"""Calendrier des epreuves a venir, et amis inscrits dessus.

Quatre sources, verifiees contre le backend reel :

    GET  api/v1/daily/schedule
        La rotation de la semaine : trois niveaux (beginner, intermediate,
        advanced), trois series chacun, avec circuit, voitures, duree et la
        liste des horaires de depart de la journee. Un seul appel.

    GET  api/v1/daily/list/{niveau}?take={n}
        Les occurrences concretes a venir : identifiant, statut, horaire.
        Le parametre est bien le NIVEAU, pas le type d'epreuve — passer
        « daily » renvoie une liste vide.

    POST api/v1/event/overview  {game, eventType, eventId}
        Le detail d'une occurrence : nombre d'inscrits, splits, et surtout
        `friends`, les amis inscrits. Absent de `daily/list`, qui ne porte ni
        inscriptions ni amis.

    GET  api/v1/special-events/{famille}
        Les hebdomadaires (`weekly`) et les epreuves speciales (`special`).
        Rien de tout cela n'est dans `daily/schedule`, qui ne porte que la
        rotation quotidienne : sans cet appel, les « WEC Weekly » et les
        « 4 Hours of Silverstone » manquaient purement et simplement.

        Un seul appel par famille porte tout : la serie **et** ses occurrences
        datees, dans `events`, chacune avec son identifiant et son nombre
        d'inscrits. Contrairement au quotidien, aucun rapprochement avec une
        seconde liste n'est necessaire.

Pourquoi `daily/schedule` porte le calendrier plutot que `daily/list` : ses
horaires couvrent exactement vingt-quatre heures et se repetent a l'identique
chaque jour de la semaine. Une fois en cache, le calendrier se prolonge donc
tout seul, jeu ferme, jusqu'a la rotation suivante. `daily/list` ne donne que
les prochaines heures.

**Ce qui exige le jeu** : les amis et le nombre d'inscrits. Ce sont des donnees
vivantes et personnelles, derriere un jeton de 30 minutes qu'on n'obtient que
par un ticket Steam — donc jeu ouvert, ou ferme depuis moins d'une demi-heure.

**Les epreuves lancees** echappent a tout cela. Des qu'une epreuve passe en
`Running` — aux essais, avant meme le depart de la course — elle disparait de
`daily/list` comme de `special-events`, et `event/overview` ne donne plus ses
`friends`. Deux parades :

    memoire locale
        Chaque epreuve vue avant son depart est retenue avec son identifiant
        (`_memoriser`). Une fois lancee, on la retrouve la.

    GET  api/v1/event/entries/{type}/{id}?page={p}&take={n}
        Les engages, qui eux restent servis pendant la course : nom et avatar
        Steam, sans identifiant de joueur. On les croise avec la liste d'amis.
        `page` commence a 1 — `page=0` renvoie la meme chose que `page=1`.
"""

import datetime
import re
from concurrent.futures import ThreadPoolExecutor

from . import cache
from .errors import HubError

NIVEAUX = ("beginner", "intermediate", "advanced")

# Les deux familles de `special-events/{famille}`. Le backend les sert par des
# appels distincts, mais leur `type` est le meme — « specialevent » — et seul
# `tier.name` les separe. C'est ce nom-la qu'on prend pour niveau.
FAMILLES_SPECIALES = ("weekly", "special")

LIBELLES_NIVEAU = {"beginner": "Débutant", "intermediate": "Intermédiaire",
                   "advanced": "Avancé", "championship": "Championnat",
                   "weekly": "Hebdo", "special": "Spéciale",
                   "specialevent": "Spéciale"}

# Occurrences demandees par niveau a `daily/list`, et epreuves enrichies par
# `event/overview`. Chaque enrichissement coute un aller-retour : pour les
# quotidiennes, on le reserve aux plus proches, les seules ou l'inscription
# d'un ami a un interet — elles n'ouvrent que trente minutes avant le depart.
PAR_NIVEAU = 8
ENRICHIES = 8

# Types enrichis sans quota. Les epreuves speciales s'inscrivent des jours a
# l'avance : un ami engage sur une course de la semaine prochaine n'est pas
# parmi les huit plus proches, et le hub le taisait.
SANS_QUOTA = {"specialevent"}

# Appels `event/overview` menes de front. Toutes les speciales, c'est une
# quarantaine d'allers-retours : en file, ils doublaient le chargement.
APPELS_SIMULTANES = 6

# Jusqu'ou prolonger les horaires en partant de la rotation. Deux jours
# suffisent a planifier, et restent dans la semaine en cours.
HORIZON_JOURS = 2
JOUR = datetime.timedelta(days=1)

# Engages demandes par page a `event/entries`. Une quotidienne en compte 80 :
# une seule page suffit presque toujours.
ENGAGES_PAR_PAGE = 100
PAGES_MAX = 10

# L'avatar Steam porte une empreinte stable, quel que soit le format demande
# (`_medium`, `_full`) : plus sur que le nom, qu'un joueur peut changer.
EMPREINTE = re.compile(r"[0-9a-f]{40}")

# Statut d'une epreuve dont les sessions ont commence. Elle quitte alors les
# listes, parfois quelques minutes AVANT son horaire affiche : mesure a 10:54:53
# pour une epreuve de 10:55. Avant (`Waiting`, `ServersStarted`,
# `ServersRunning`), elle est listee et `friends` est servi.
STATUT_LANCEE = "Running"

# Ce qu'on retient d'une epreuve pour la reconstruire une fois lancee.
CHAMPS_MEMOIRE = ("identifiant", "type", "niveau", "nom", "circuit", "debut",
                  "duree", "voitures", "series_id", "rang_requis", "fin")


def _moment(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _iso(moment):
    return moment.astimezone(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def _minutes(duree):
    """Convertit « 1h12m30s » en minutes."""
    total, nombre = 0, ""
    for caractere in str(duree or ""):
        if caractere.isdigit():
            nombre += caractere
        elif nombre:
            total += int(nombre) * {"h": 60, "m": 1, "s": 1 / 60}.get(caractere, 0)
            nombre = ""
    return total


def joli_circuit(brut):
    """Rend lisible un nom de circuit tel que le backend l'ecrit.

    La rotation donne des identifiants techniques — « SilverstoneELMS »,
    « PortimaoWEC_2023 », « PaulRicard_2025 ». On enleve le millesime et on
    separe les mots colles, ce qui detache aussi le sigle du championnat.
    """
    nom = str(brut or "").replace("_", " ").strip()
    morceaux = nom.split()
    if morceaux and len(morceaux[-1]) == 4 and morceaux[-1].isdigit():
        morceaux = morceaux[:-1]          # millesime : sans interet ici
    nom = " ".join(morceaux)
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", nom) or "?"


def maintenant():
    return datetime.datetime.now(datetime.timezone.utc)


class Ami:
    """Un ami inscrit a une epreuve."""

    def __init__(self, brut):
        self.identifiant = brut.get("id") or ""
        self.nom = brut.get("name") or brut.get("username") or "?"
        self.avatar = brut.get("avatar") or ""

    @property
    def empreinte(self):
        trouvee = EMPREINTE.search(self.avatar)
        return trouvee.group(0) if trouvee else ""


class Epreuve:
    """Une occurrence datee d'une serie."""

    def __init__(self, niveau, nom, circuit, debut, duree=0, voitures=(),
                 series_id="", type_epreuve="daily"):
        self.niveau = niveau
        self.nom = nom or "?"
        self.circuit = circuit or "?"
        self.debut = debut or ""
        self.duree = duree
        self.voitures = list(voitures)
        self.series_id = series_id
        self.type = type_epreuve

        # Renseignes seulement quand le backend a repondu (voir `enrichir`).
        self.identifiant = ""
        self.statut = ""
        self.inscrits = None
        self.splits = 0
        self.complet = False
        self.amis = []
        self.rang_requis = ""
        # Fin de course annoncee par le backend (`raceEndsAt`). La duree de la
        # rotation ne compte que la course, sans essais ni qualification.
        self.fin = ""

    # --- horaires ---

    def minutes_avant(self, repere=None):
        debut = _moment(self.debut)
        if debut is None:
            return None
        return (debut - (repere or maintenant())).total_seconds() / 60

    @property
    def passee(self):
        fin = _moment(self.fin)
        if fin is not None:
            return maintenant() > fin
        restant = self.minutes_avant()
        return restant is not None and restant < -max(self.duree, 60)

    @property
    def en_cours(self):
        restant = self.minutes_avant()
        return restant is not None and restant <= 0 and not self.passee

    @property
    def lancee(self):
        """Serveurs en piste : le backend le dit parfois avant l'horaire."""
        return not self.passee and (self.statut == STATUT_LANCEE or self.en_cours)

    # --- memoire locale ---

    def memoire(self):
        return {champ: getattr(self, champ) for champ in CHAMPS_MEMOIRE}

    @classmethod
    def depuis_memoire(cls, brut):
        epreuve = cls(brut.get("niveau"), brut.get("nom"), brut.get("circuit"),
                      brut.get("debut"), brut.get("duree") or 0,
                      brut.get("voitures") or (), brut.get("series_id") or "",
                      brut.get("type") or "daily")
        epreuve.identifiant = brut.get("identifiant") or ""
        epreuve.rang_requis = brut.get("rang_requis") or ""
        epreuve.fin = brut.get("fin") or ""
        return epreuve

    def compte_a_rebours(self):
        """« dans 12 min », « dans 2 h 05 », « en cours », « terminée »."""
        restant = self.minutes_avant()
        if restant is None:
            return "?"
        if restant <= 0 or self.lancee:
            return "terminée" if self.passee else "en cours"
        if restant < 60:
            return f"dans {restant:.0f} min"
        heures, minutes = divmod(int(restant), 60)
        if heures < 24:
            return f"dans {heures} h {minutes:02d}"
        return f"dans {heures // 24} j {heures % 24} h"

    # --- enrichissement ---

    def rattacher(self, brut):
        """Associe l'occurrence concrete renvoyee par `daily/list`."""
        config = brut.get("configuration") or {}
        exigence = (config.get("tier") or {}).get("entryRequirement") or {}
        self.identifiant = brut.get("id") or ""
        self.statut = brut.get("status") or ""
        self.type = brut.get("type") or self.type
        self.fin = brut.get("raceEndsAt") or self.fin
        self.rang_requis = " ".join(
            str(x) for x in (exigence.get("rank"), exigence.get("tier")) if x)

    def detailler(self, brut):
        """Ajoute inscrits, splits et amis, depuis `event/overview`."""
        # Les epreuves speciales portent deja leurs inscrits : une reponse qui
        # ne les redonne pas ne doit pas les effacer.
        total = (brut.get("registered") or {}).get("total")
        if total is not None:
            self.inscrits = total
        self.splits = brut.get("totalSplits") or 0
        self.complet = bool(brut.get("eventFull"))
        self.amis = [Ami(a) for a in (brut.get("friends") or [])]
        self.statut = brut.get("status") or self.statut
        self.fin = brut.get("raceEndsAt") or self.fin


class Calendrier:
    """Les epreuves a venir, avec l'origine des donnees."""

    def __init__(self, epreuves, date=None, hors_ligne=False, amis_connus=False):
        self.epreuves = sorted(epreuves, key=lambda e: e.debut or "")
        self.date = date
        self.hors_ligne = hors_ligne
        # False quand on n'a pas pu interroger le backend : l'absence d'amis
        # ne veut alors rien dire, et l'interface doit le distinguer.
        self.amis_connus = amis_connus

    def a_venir(self):
        return [e for e in self.epreuves if not e.passee]

    @property
    def avec_amis(self):
        return [e for e in self.epreuves if e.amis]


# --- construction depuis la rotation -----------------------------------------

def _epreuves_depuis_rotation(rotation, depuis=None, horizon=HORIZON_JOURS):
    """Developpe la rotation en occurrences datees.

    Les horaires couvrent une journee et se repetent a l'identique : on les
    rejoue jour apres jour pour couvrir l'horizon demande.
    """
    depuis = depuis or maintenant()
    limite = depuis + datetime.timedelta(days=horizon)
    epreuves = []

    for niveau, series in (rotation.get("tiers") or {}).items():
        for serie in series or []:
            duree = _minutes(serie.get("duration"))
            for horaire in (serie.get("times") or []):
                debut = _moment(horaire)
                if debut is None:
                    continue
                jour = 0
                while jour <= horizon:
                    moment_epreuve = debut + jour * JOUR
                    jour += 1
                    if moment_epreuve > limite:
                        break
                    if (moment_epreuve - depuis).total_seconds() < -duree * 60:
                        continue
                    epreuves.append(Epreuve(
                        niveau=niveau,
                        nom=serie.get("eventname"),
                        circuit=joli_circuit(serie.get("tracklayout")
                                             or serie.get("track")),
                        debut=_iso(moment_epreuve),
                        duree=duree,
                        voitures=serie.get("cars") or [],
                        series_id=serie.get("seriesid") or ""))
    return epreuves


def _epreuves_speciales(series, depuis=None):
    """Developpe les hebdomadaires et les epreuves speciales en occurrences.

    Rien a rejouer ici, contrairement au quotidien : `events` porte deja les
    departs concrets, chacun avec son identifiant et ses inscrits. On les prend
    tels quels, ce qui rend le nombre d'inscrits disponible **sans** passer par
    `event/overview` — seuls les amis exigent encore un aller-retour.
    """
    depuis = depuis or maintenant()
    epreuves = []

    for serie in series or []:
        config = serie.get("configuration") or {}
        contenu = config.get("content") or {}
        piste = contenu.get("track") or {}
        palier = serie.get("tier") or {}
        exigence = palier.get("entryRequirement") or {}

        # Une epreuve speciale enchaine essais, qualification et course : son
        # depart est celui de la premiere session, sa duree leur somme, temps
        # d'attente compris. Sans cela une 4 heures serait declaree terminee
        # vingt minutes apres son debut.
        duree = sum(_minutes(session.get("duration")) + _minutes(session.get("waitTime"))
                    for session in (config.get("sessions") or []))

        voitures = [voiture.get("friendly") or voiture.get("name")
                    for voiture in (contenu.get("cars") or [])]

        for occurrence in (serie.get("events") or []):
            debut = _moment(occurrence.get("starts"))
            if debut is None or (debut - depuis).total_seconds() < -duree * 60:
                continue
            epreuve = Epreuve(
                niveau=palier.get("name") or "special",
                nom=serie.get("title"),
                circuit=joli_circuit(piste.get("friendly") or piste.get("name")),
                debut=_iso(debut),
                duree=duree,
                voitures=voitures,
                series_id=serie.get("seriesId") or "",
                type_epreuve=serie.get("type") or "specialevent")
            epreuve.identifiant = occurrence.get("id") or ""
            epreuve.inscrits = occurrence.get("registrations")
            epreuve.rang_requis = " ".join(
                str(x) for x in (exigence.get("rank"), exigence.get("tier")) if x)
            epreuves.append(epreuve)

    return epreuves


def _epreuves_championnats(championnats, depuis=None):
    """La prochaine manche de chaque championnat actif."""
    depuis = depuis or maintenant()
    epreuves = []
    for championnat in championnats or []:
        for manche in (championnat.get("rounds") or []):
            debut = _moment(manche.get("startsAt"))
            if debut is None or debut < depuis:
                continue
            piste = manche.get("track") or {}
            epreuve = Epreuve(
                niveau="championship",
                nom=championnat.get("name"),
                circuit=joli_circuit(piste.get("friendly") or piste.get("name")),
                debut=_iso(debut),
                duree=sum(_minutes(s.get("duration"))
                          for s in (manche.get("sessions") or [])),
                series_id=championnat.get("id") or "",
                type_epreuve="championship")
            epreuve.inscrits = championnat.get("registrations")
            epreuves.append(epreuve)
            break  # une seule manche a venir par championnat
    return epreuves


# --- chargement ---------------------------------------------------------------

def charger(ctx, enrichies=ENRICHIES):
    """Interroge le backend, met la rotation en cache, renvoie le calendrier."""
    ros = ctx.raceos
    ros.authenticate()

    rotation = ros.fetch("api/v1/daily/schedule", method="GET") or {}
    epreuves = _epreuves_depuis_rotation(rotation)

    speciales = []
    for famille in FAMILLES_SPECIALES:
        try:
            speciales.extend(ros.fetch(f"api/v1/special-events/{famille}",
                                       method="GET") or [])
        except HubError:
            continue  # une famille muette n'emporte pas les autres
    epreuves.extend(_epreuves_speciales(speciales))

    championnats = []
    try:
        championnats = ros.fetch("api/v1/championships/active?esports=false",
                                 method="GET") or []
        epreuves.extend(_epreuves_championnats(championnats))
    except HubError:
        pass  # le calendrier quotidien vaut deja la peine d'etre affiche

    # Les occurrences concretes portent l'identifiant, sans lequel on ne peut
    # pas demander le detail. On les rapproche par serie et horaire de depart.
    concretes = {}
    for niveau in NIVEAUX:
        try:
            for brut in ros.fetch(f"api/v1/daily/list/{niveau}?take={PAR_NIVEAU}",
                                  method="GET") or []:
                debut = _moment((brut.get("configuration") or {}).get("starts")
                                or brut.get("raceStartsAt"))
                if debut is not None:
                    concretes[(brut.get("seriesId"), _iso(debut))] = brut
        except HubError:
            continue

    for epreuve in epreuves:
        brut = concretes.get((epreuve.series_id, epreuve.debut))
        if brut is not None:
            epreuve.rattacher(brut)

    _memoriser(epreuves)
    _enrichir(ros, epreuves, enrichies)

    try:
        cache.save_calendrier({"rotation": rotation,
                               "speciales": _resume_speciales(speciales),
                               "championnats": _resume_championnats(championnats)})
    except OSError:
        pass

    return Calendrier(epreuves, amis_connus=True)


def _memoriser(epreuves):
    """Retrouve les epreuves lancees, et retient celles qui ne le sont pas encore.

    Le backend retire une epreuve de `daily/list` et de `special-events` des
    qu'elle passe en `Running`. Sans memoire, l'identifiant d'une quotidienne
    lancee est perdu — et une epreuve speciale lancee disparait tout entiere
    du calendrier, six heures durant pour une course de six heures. Or c'est
    precisement la qu'on cherche ses amis.

    Limite assumee : une epreuve deja lancee au premier lancement du hub n'a
    jamais ete vue, et reste introuvable.
    """
    memoire = cache.load_occurrences()
    identifiees = {e.identifiant for e in epreuves if e.identifiant}
    par_depart = {(e.series_id, e.debut): e for e in epreuves}

    # Retenue, pas terminee, mais absente des listes : elle est donc lancee —
    # y compris quand son horaire affiche n'est pas encore atteint.
    for brut in memoire.values():
        connue = Epreuve.depuis_memoire(brut)
        if connue.identifiant in identifiees or connue.passee:
            continue
        connue.statut = STATUT_LANCEE
        existante = par_depart.get((connue.series_id, connue.debut))
        if existante is None:
            epreuves.append(connue)          # speciale : absente de la reponse
        elif not existante.identifiant:
            existante.identifiant = connue.identifiant
            existante.type = connue.type
            existante.statut = STATUT_LANCEE

    retenues = {cle: brut for cle, brut in memoire.items()
                if not Epreuve.depuis_memoire(brut).passee}
    for epreuve in epreuves:
        if epreuve.identifiant and not epreuve.passee:
            retenues[epreuve.identifiant] = epreuve.memoire()
    try:
        cache.save_occurrences(retenues)
    except OSError:
        pass


def _engages(ros, epreuve):
    """Tous les engages d'une epreuve, page apres page."""
    engages = []
    for page in range(1, PAGES_MAX + 1):
        lot = ros.fetch(f"api/v1/event/entries/{epreuve.type}/{epreuve.identifiant}"
                        f"?page={page}&take={ENGAGES_PAR_PAGE}", method="GET") or []
        engages.extend(lot)
        if len(lot) < ENGAGES_PAR_PAGE:
            break
    return engages


def _amis_parmi(engages, amis):
    """Les amis presents parmi les engages, equipiers compris.

    `event/entries` ne donne pas d'identifiant de joueur : on reconnait un ami
    a l'empreinte de son avatar Steam, a defaut a son nom.
    """
    par_empreinte = {a.empreinte: a for a in amis if a.empreinte}
    par_nom = {a.nom.casefold(): a for a in amis}
    trouves = []
    for engage in engages:
        for pilote in [engage] + list(engage.get("teamMembers") or []):
            candidat = Ami(pilote)
            ami = (par_empreinte.get(candidat.empreinte)
                   or par_nom.get(candidat.nom.casefold()))
            if ami is not None and ami not in trouves:
                trouves.append(ami)
    return trouves


def _enrichir(ros, epreuves, combien):
    """Ajoute splits et amis aux prochaines epreuves identifiees.

    Le quota vaut **par type d'epreuve**, et non sur l'ensemble. Les
    quotidiennes partant toutes les dix minutes, les plus proches sont
    forcement quotidiennes : un quota global aurait condamne les epreuves
    speciales a ne jamais montrer leurs amis inscrits, alors que ce sont
    justement celles qu'on prepare a l'avance. Les types de `SANS_QUOTA`
    sont enrichis en entier.

    Une epreuve lancee ne publie plus ses `friends` : on lit alors ses engages,
    et la liste d'amis n'est demandee qu'a ce moment-la.
    """
    proches = []
    for type_epreuve in {e.type for e in epreuves}:
        limite = None if type_epreuve in SANS_QUOTA else combien
        proches.extend(
            [e for e in sorted(epreuves, key=lambda e: e.debut)
             if e.type == type_epreuve and e.identifiant and not e.passee][:limite])

    with ThreadPoolExecutor(max_workers=APPELS_SIMULTANES) as appels:
        details = list(appels.map(lambda e: _detail(ros, e), proches))

    amis = None
    for epreuve, detail in zip(proches, details):
        if isinstance(detail, dict):
            epreuve.detailler(detail)

        if not epreuve.lancee or epreuve.amis:
            continue
        try:
            if amis is None:
                amis = [Ami(a) for a in ros.friends()]
            if amis:
                epreuve.amis = _amis_parmi(_engages(ros, epreuve), amis)
        except HubError:
            continue


def _detail(ros, epreuve):
    """La reponse de `event/overview` pour une epreuve, ou None."""
    try:
        return ros.fetch("api/v1/event/overview",
                         body={"game": "lmu", "eventType": epreuve.type,
                               "eventId": epreuve.identifiant},
                         method="POST")
    except HubError:
        return None


def _resume_speciales(series):
    """Ne garde des epreuves speciales que ce que le calendrier affiche.

    La reponse brute pese plusieurs centaines de kilo-octets : reglages du
    serveur, meteo minute par minute, livrees de chaque voiture. Le cache n'a
    besoin que des departs, du circuit et de la duree.
    """
    resume = []
    for serie in series or []:
        config = serie.get("configuration") or {}
        contenu = config.get("content") or {}
        piste = contenu.get("track") or {}
        resume.append({
            "seriesId": serie.get("seriesId"),
            "title": serie.get("title"),
            "type": serie.get("type"),
            "tier": serie.get("tier"),
            "events": [{"id": e.get("id"), "starts": e.get("starts"),
                        "registrations": e.get("registrations")}
                       for e in (serie.get("events") or [])],
            "configuration": {
                "sessions": [{"duration": x.get("duration"),
                              "waitTime": x.get("waitTime")}
                             for x in (config.get("sessions") or [])],
                "content": {
                    "track": {"name": piste.get("name"),
                              "friendly": piste.get("friendly")},
                    "cars": [{"friendly": c.get("friendly"), "name": c.get("name")}
                             for c in (contenu.get("cars") or [])],
                },
            },
        })
    return resume


def _resume_championnats(championnats):
    """Ne garde des championnats que la prochaine manche, pour le cache."""
    resume = []
    for championnat in championnats or []:
        resume.append({
            "id": championnat.get("id"),
            "name": championnat.get("name"),
            "registrations": championnat.get("registrations"),
            "rounds": [{"startsAt": m.get("startsAt"),
                        "track": m.get("track"),
                        "sessions": [{"duration": s.get("duration")}
                                     for s in (m.get("sessions") or [])]}
                       for m in (championnat.get("rounds") or [])],
        })
    return resume


def ouvrir(ctx):
    """Calendrier en ligne si le backend repond, sinon depuis la rotation en cache.

    Le repli n'est pas degrade pour les horaires : la rotation se rejoue a
    l'identique chaque jour, donc les departs restent exacts jusqu'a la
    rotation suivante. Seuls les inscrits et les amis manquent.

    Les epreuves speciales, elles, ne se rejouent pas : leurs departs sont
    dates une fois pour toutes. Le cache les sert donc exactement, mais la
    liste se vide a mesure qu'elles passent, au lieu de se prolonger.
    """
    try:
        return charger(ctx)
    except HubError:
        donnees = cache.load_calendrier()
        rotation = (donnees or {}).get("rotation")
        if not rotation:
            raise
        epreuves = _epreuves_depuis_rotation(rotation)
        epreuves.extend(_epreuves_speciales((donnees or {}).get("speciales")))
        epreuves.extend(_epreuves_championnats((donnees or {}).get("championnats")))
        return Calendrier(epreuves, date=donnees.get("fetchedAt"), hors_ligne=True)
