"""Cache local du hub.

Deux usages :

- **session** : l'accessToken RaceOS, valable 30 minutes. Tant qu'il n'a pas
  expire, le hub interroge le backend sans que le jeu soit lance.
- **snapshot** : les dernieres valeurs connues, pour une consultation hors
  ligne quand ni le jeu ni un token valide ne sont disponibles.

Le fichier de session contient un jeton d'authentification : il est ecrit en
acces restreint et ignore par git.
"""

import datetime
import json
import os
import shutil
import sys
from pathlib import Path

# Noms portes par l'application avant celui-ci. Le cache les suit : sinon un
# renommage ferait perdre la configuration des molettes et l'historique des
# ratings — qui, lui, ne se reconstitue pas.
DOSSIER = "LMU Central"
ANCIENS_DOSSIERS = ("LMU Hub",)

# L'historique se fusionne au lieu de s'ecraser : chaque releve vaut le
# pourcentage exact d'une course, et rien ne permet de le retrouver apres coup.
HISTORIQUE_NOM = "historique-ratings.json"

# Suffixe donne a l'ancien dossier une fois repris. Rien n'est supprime : on
# le met simplement hors de portee, pour ne pas refaire la fusion a chaque
# lancement ni ressusciter ce que l'utilisateur aurait efface.
SUFFIXE_REPRIS = " (repris)"


def _fusionner_historique(source, cible):
    """Reunit deux historiques de ratings, dedoublonnes par date."""
    points = {}
    for chemin in (source, cible):
        try:
            lus = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(lus, list):
            points.update({p.get("date"): p for p in lus if isinstance(p, dict)})

    ordonnes = [points[d] for d in sorted(p for p in points if p)]
    cible.write_text(json.dumps(ordonnes, indent=2, ensure_ascii=False),
                     encoding="utf-8")


def _recuperer_ancien_cache(base, dossier):
    """Reprend le cache laisse par une version portant un autre nom.

    On fusionne au lieu de renommer : les deux dossiers peuvent coexister si
    l'application a tourne sous les deux noms, et c'est justement le cas ou un
    simple renommage abandonnerait les relevés les plus recents.
    """
    for ancien in ANCIENS_DOSSIERS:
        source = base / ancien
        if not source.is_dir():
            continue

        dossier.mkdir(parents=True, exist_ok=True)
        for fichier in source.iterdir():
            if not fichier.is_file():
                continue
            arrivee = dossier / fichier.name
            try:
                if fichier.name == HISTORIQUE_NOM and arrivee.exists():
                    _fusionner_historique(fichier, arrivee)
                elif not arrivee.exists() or \
                        fichier.stat().st_mtime > arrivee.stat().st_mtime:
                    shutil.copy2(fichier, arrivee)
            except OSError:
                pass  # un fichier illisible ne doit pas empecher le demarrage

        try:
            source.rename(base / (ancien + SUFFIXE_REPRIS))
        except OSError:
            pass  # dossier verrouille : la fusion se refera au prochain coup


def _cache_dir():
    """Emplacement du cache.

    En .exe, `__file__` pointe vers un dossier temporaire efface a chaque
    lancement : on ecrit alors dans le profil utilisateur pour que la session
    et l'instantane survivent d'une execution a l'autre.
    """
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"))
        dossier = base / DOSSIER
        _recuperer_ancien_cache(base, dossier)
        return dossier
    return Path(__file__).resolve().parents[2] / ".cache"


CACHE_DIR = _cache_dir()
SESSION_FILE = CACHE_DIR / "session.json"
HISTORIQUE_FILE = CACHE_DIR / HISTORIQUE_NOM
SNAPSHOT_FILE = CACHE_DIR / "snapshot.json"
COURSES_FILE = CACHE_DIR / "courses.json"
CALENDRIER_FILE = CACHE_DIR / "calendrier.json"
OCCURRENCES_FILE = CACHE_DIR / "occurrences.json"

# Marge avant expiration : on ne reutilise pas un token qui expire dans l'instant.
EXPIRY_MARGIN = datetime.timedelta(seconds=60)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_expiry(value):
    """Lit un horodatage ISO renvoye par raceos.gg.

    Le backend emet des nanosecondes (9 decimales) la ou Python n'en accepte
    que 6 : on tronque la fraction de seconde avant de parser.
    """
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    if "." in text:
        head, _, rest = text.partition(".")
        digits = ""
        while rest and rest[0].isdigit():
            digits, rest = digits + rest[0], rest[1:]
        text = head + "." + digits[:6] + (rest or "+00:00")
    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        return None


def _write(path, payload, private=False):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if private and os.name == "posix":
        os.chmod(path, 0o600)


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# --- session ---

def save_session(access_token, expires_at, player):
    """Ecrit la session et renvoie la date de capture du profil.

    Dater le profil est indispensable : il est resservi tel quel pendant les
    30 minutes du jeton, et rien d'autre ne permettrait de dire que le rating
    affiche est celui d'avant la derniere course.
    """
    fetched_at = _now().isoformat(timespec="seconds")
    _write(SESSION_FILE, {
        "accessToken": access_token,
        "expiresAt": expires_at,
        "fetchedAt": fetched_at,
        "player": player,
    }, private=True)
    return fetched_at


def load_session():
    """Session encore valide, ou None."""
    data = _read(SESSION_FILE)
    if not data or not data.get("accessToken"):
        return None
    expiry = _parse_expiry(data.get("expiresAt"))
    if expiry is None or _now() + EXPIRY_MARGIN >= expiry:
        return None
    return data


def session_expiry():
    """Minutes restantes sur la session en cache, ou None."""
    data = load_session()
    if not data:
        return None
    expiry = _parse_expiry(data.get("expiresAt"))
    return max(0, (expiry - _now()).total_seconds() / 60)


def clear_session():
    SESSION_FILE.unlink(missing_ok=True)


# --- snapshot ---

def save_snapshot(payload):
    data = dict(payload)
    data["fetchedAt"] = _now().isoformat(timespec="seconds")
    _write(SNAPSHOT_FILE, data)


def load_snapshot():
    return _read(SNAPSHOT_FILE)


# --- courses ---

def save_courses(courses):
    """Ajoute ces courses au cache, sans perdre les precedentes.

    Fusion par identifiant plutot qu'ecrasement : une session ou l'on ne
    deroule que la premiere page ne doit pas rabougrir un cache qui contenait
    tout l'historique. Une course disputee ne change plus, la garder est sans
    risque.
    """
    connues = {}
    for lot in ((_read(COURSES_FILE) or {}).get("courses") or [], courses):
        for course in lot:
            connues[course.get("identifiant") or course.get("date")] = course

    _write(COURSES_FILE, {
        "fetchedAt": _now().isoformat(timespec="seconds"),
        "courses": sorted(connues.values(),
                          key=lambda c: c.get("date") or "", reverse=True),
    })


def load_courses():
    return _read(COURSES_FILE)


# --- calendrier ---

def save_calendrier(donnees):
    """Remplace le calendrier en cache.

    On garde la rotation de la semaine, pas les occurrences : ses horaires se
    rejouent a l'identique chaque jour, donc le calendrier se reconstruit
    exactement, jeu ferme, jusqu'a la rotation suivante.

    Les epreuves speciales font exception : n'ayant pas de rotation, ce sont
    leurs departs dates qu'on garde, reduits a ce que le calendrier affiche.
    """
    charge = {"fetchedAt": _now().isoformat(timespec="seconds")}
    charge.update(donnees)
    _write(CALENDRIER_FILE, charge)


def load_calendrier():
    return _read(CALENDRIER_FILE)


def save_occurrences(occurrences):
    """Remplace la memoire des epreuves vues avant leur depart.

    Le backend retire une epreuve de ses listes des qu'elle est lancee : sans
    cette memoire, son identifiant — et donc ses engages — serait perdu
    justement pendant qu'elle roule. Voir `calendrier._memoriser`.
    """
    _write(OCCURRENCES_FILE, {"fetchedAt": _now().isoformat(timespec="seconds"),
                              "occurrences": occurrences})


def load_occurrences():
    return (_read(OCCURRENCES_FILE) or {}).get("occurrences") or {}
