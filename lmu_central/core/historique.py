"""Historique des ratings, pour connaitre le pourcentage exact gagne ou perdu.

Pourquoi le construire soi-meme : le backend ne le publie nulle part. Les
resultats de course exposent `driverRankAdjustment`, un entier de -3 a +3 que
le jeu affiche sous forme de chevrons — une direction, pas une valeur. Et sur
tous les endpoints sauf `/authenticate`, `elo` vaut 0 et `progress` est arrondi
a la dizaine.

Le seul endroit ou la valeur exacte existe est la reponse d'authentification.
On la releve donc a chaque consultation et on garde la trace : la difference
entre deux releves donne le gain ou la perte reelle.

Consequence a assumer : l'historique demarre au premier lancement du hub. Les
courses anterieures ne peuvent pas etre reconstituees.
"""

import datetime
import json

from . import cache

FICHIER = cache.HISTORIQUE_FILE

# Deux releves dont ni l'ELO ni le rating de securite ne bougent d'au moins ce
# seuil decrivent le meme etat : on ne cree pas de point pour une simple
# consultation.
SEUIL_ELO = 0.0001


def _a_bouge(avant, apres):
    """Vrai si le DR ou le SR a change entre deux releves.

    Les deux comptent : une course propre peut ne rien changer au DR et faire
    monter le SR, et ce gain-la est aussi affiche dans l'historique.
    """
    return (abs(apres["drElo"] - avant["drElo"]) >= SEUIL_ELO
            or abs(apres["srRating"] - avant["srRating"]) >= SEUIL_ELO)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _lire():
    try:
        données = json.loads(FICHIER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return données if isinstance(données, list) else []


def _ecrire(points):
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    FICHIER.write_text(json.dumps(points, indent=2, ensure_ascii=False),
                       encoding="utf-8")


def point_depuis_player(player):
    """Convertit un profil brut (reponse d'authentification) en releve."""
    return _point(player.get("driverRank") or {}, player.get("safetyRank") or {})


def point_depuis(ratings):
    """Convertit un chargement de ratings en releve."""
    return _point(ratings.driver_rank, ratings.safety_rank)


def _point(dr, sr):
    return {
        "date": _now().isoformat(timespec="seconds"),
        "drElo": dr.get("elo", 0.0),
        "drRank": dr.get("rank"),
        "drTier": dr.get("tier"),
        "drProgress": dr.get("progress", 0.0),
        "srRating": sr.get("rating", 0.0),
        "srRank": sr.get("rank"),
        "srTier": sr.get("tier"),
        "srProgress": sr.get("progress", 0.0),
    }


def enregistrer(ratings):
    """Releve les valeurs si elles ont bouge. Renvoie le point ajoute, ou None.

    Les donnees hors ligne et les valeurs tronquees (elo a 0) sont ignorees :
    elles fausseraient les ecarts.
    """
    if ratings.offline or not ratings.driver_rank.get("elo"):
        return None

    points = _lire()
    nouveau = point_depuis(ratings)
    if points and not _a_bouge(points[-1], nouveau):
        return None

    points.append(nouveau)
    _ecrire(points)
    return nouveau


def _ecart_progress(avant, apres, cle_progress, cle_rank, cle_tier):
    """Ecart de progression en points de pourcentage, changement de tier inclus.

    Passer de Silver 3 a 95 % a Gold 1 a 10 % est un gain de 15 points, pas une
    chute de 85 : on ajoute 100 points par tier franchi.
    """
    ordre = ["Bronze", "Silver", "Gold", "Platinum"]

    def absolu(p):
        rang = p.get(cle_rank)
        indice = ordre.index(rang) if rang in ordre else 0
        return (indice * 3 + (p.get(cle_tier) or 0)) * 100 + (p.get(cle_progress) or 0)

    return absolu(apres) - absolu(avant)


class Variation:
    """Ce qui a change entre deux releves — en pratique, une course."""

    def __init__(self, avant, apres):
        self.avant, self.apres = avant, apres
        self.date = apres["date"]
        self.dr_elo = apres["drElo"] - avant["drElo"]
        self.dr_pct = _ecart_progress(avant, apres, "drProgress", "drRank", "drTier")
        self.sr_val = apres["srRating"] - avant["srRating"]
        self.sr_pct = _ecart_progress(avant, apres, "srProgress", "srRank", "srTier")

    @property
    def rang_change(self):
        return (self.avant["drRank"], self.avant["drTier"]) != \
               (self.apres["drRank"], self.apres["drTier"])

    @property
    def rang_apres(self):
        return f"{self.apres['drRank']} {self.apres['drTier']}"

    @property
    def sr_rang_apres(self):
        return f"{self.apres['srRank']} {self.apres['srTier']}"


def variations(limite=10):
    """Les `limite` dernieres variations, de la plus recente a la plus ancienne."""
    points = _lire()
    if len(points) < 2:
        return []
    # Deux releves identiques (une consultation, ou deux caches fusionnes) ne
    # decrivent aucune course : les garder attribuerait un +0,00 % a une
    # epreuve qui a bel et bien fait bouger le rating.
    paires = [Variation(points[i - 1], points[i]) for i in range(1, len(points))
              if _a_bouge(points[i - 1], points[i])]
    return list(reversed(paires))[:limite]


def nombre_de_points():
    return len(_lire())


def effacer():
    FICHIER.unlink(missing_ok=True)


def relever(ctx):
    """Releve immediat de l'ELO exact, en reauthentifiant.

    Utilise a la fin d'une course : c'est le seul moment ou la nouvelle valeur
    est disponible, et `/authenticate` est le seul endpoint a la donner. Un
    seul aller-retour, sans charger amis ni statistiques.
    """
    player = ctx.raceos.authenticate(force=True)
    dr = (player or {}).get("driverRank") or {}
    if not dr.get("elo"):
        return None

    points = _lire()
    nouveau = point_depuis_player(player)
    if points and not _a_bouge(points[-1], nouveau):
        return None

    points.append(nouveau)
    _ecrire(points)
    return nouveau
