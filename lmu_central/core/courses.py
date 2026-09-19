"""Historique de courses, tel que le backend le publie.

`GET api/v1/results` renvoie les epreuves disputees, avec pour chaque pilote sa
position et un `driverRankAdjustment` de -3 a +3 — le nombre de crans gagnes ou
perdus, que le jeu affiche sous forme de chevrons. Le pourcentage exact n'y
figure pas : il vient de l'historique local (voir `historique.py`), qu'on
rapproche ici de chaque course.

Le chargement est incremental : une page de 20 par type d'epreuve a la fois, a
la demande. Tout tirer d'un coup bloquait la vue plusieurs secondes.

Les types avancent **ensemble**, une page de chacun par tour. Les epuiser l'un
apres l'autre reviendrait a cacher les epreuves rares derriere le quotidien :
avec mille courses journalieres devant, une epreuve speciale disputee la veille
n'apparaissait jamais.

Ce qui arrive est garde en cache. Le backend n'est joignable que le jeu ouvert
ou dans les 30 minutes qui suivent : sans cache, la vue serait vide le reste du
temps, alors que les courses passees, elles, ne changent plus.
"""

from . import cache
from .errors import HubError

# Les seuls `eventType` que `results` reconnaisse, mesures contre le backend.
# « special » etait faux : il renvoie `null`, exactement comme un type invente.
# Le bon nom est « specialevent », et il couvre les deux familles de l'onglet
# du jeu — hebdomadaires et epreuves speciales, que seul `tier` distingue.
# « championship » renvoie `null` lui aussi. On le garde faute de pouvoir
# trancher : le backend repond pareil a un type inconnu et a un type valide
# sans resultat, et aucun championnat n'a encore ete dispute pour le verifier.
# Le cout est d'un aller-retour par session, le type etant aussitot epuise.
TYPES = ("daily", "specialevent", "championship")
PAR_PAGE = 20
PAGES_MAX = 50  # garde-fou : 1000 courses au plus par type


class Course:
    """Une epreuve disputee, du point de vue du joueur.

    Construite depuis la reponse du backend (`depuis_evenement`) ou depuis le
    cache (`__init__` sur le dictionnaire rendu par `en_cache`). On ne garde
    que les champs affiches : une reponse brute pese une dizaine de kilo-octets
    par course, la forme reduite quelques centaines d'octets.
    """

    CHAMPS = ("date", "titre", "circuit", "tier", "split", "type", "identifiant",
              "dr_crans", "sr_crans", "joker", "position", "grille", "classe",
              "voiture", "statut")

    def __init__(self, champs):
        for nom in self.CHAMPS:
            setattr(self, nom, champs.get(nom))
        self.date = self.date or ""
        self.titre = self.titre or "?"
        self.circuit = self.circuit or "?"
        self.statut = (self.statut or "").strip()
        self.position = self.position or "-"
        self.grille = self.grille or "-"

        # Rempli par rapprocher() quand l'historique local couvre cette course.
        self.variation = None
        self.variation_partagee = 1

    @classmethod
    def depuis_evenement(cls, evenement, nk_id, steam_id):
        pilote = next((d for d in (evenement.get("drivers") or [])
                       if d.get("nkId") == nk_id or d.get("steamId") == steam_id), {})
        resultat = cls._resultat(evenement, "race", steam_id)
        return cls({
            "date": evenement.get("date"),
            "titre": evenement.get("title"),
            "circuit": evenement.get("track"),
            "tier": evenement.get("tier") or "",
            "split": evenement.get("splitNo") or "",
            "type": evenement.get("eventType") or "",
            "identifiant": evenement.get("eventId") or "",
            "dr_crans": pilote.get("driverRankAdjustment") or 0,
            "sr_crans": pilote.get("safetyRankAdjustment") or 0,
            "joker": bool(pilote.get("jokerPlayed")),
            "position": resultat.get("position"),
            "grille": resultat.get("gridPos"),
            "classe": resultat.get("carClass") or "",
            "voiture": resultat.get("carType") or "",
            # Valeurs rencontrees : "Finished Normally", "DNF", "DQ", "None".
            "statut": resultat.get("finishStatus"),
        })

    def en_cache(self):
        return {nom: getattr(self, nom) for nom in self.CHAMPS}

    @staticmethod
    def _resultat(evenement, session, steam_id):
        bloc = evenement.get(session) or {}
        for manche in (bloc.get("races") or []):
            for ligne in (manche.get("results") or []):
                if ligne.get("steamId") == steam_id:
                    return ligne
        return {}

    @property
    def abandon(self):
        return self.statut.upper() in ("DNF", "DQ")

    @property
    def exacte(self):
        """True si le pourcentage exact est connu pour cette course seule."""
        return self.variation is not None and self.variation_partagee == 1

    @property
    def rang(self):
        """Position numerique, ou None (abandon, donnee absente)."""
        return int(self.position) if str(self.position).isdigit() else None

    @property
    def victoire(self):
        return self.rang == 1 and not self.abandon

    @property
    def podium(self):
        return self.rang is not None and self.rang <= 3 and not self.abandon


class Chargeur:
    """Recupere les courses page par page, a la demande.

    Les types d'epreuve avancent **de front** : chaque tour lit une page de
    chacun, et non le suivant une fois le precedent epuise. L'ordre sequentiel
    enterrait les epreuves rares — il fallait derouler jusqu'a mille courses
    quotidiennes avant de voir sa premiere epreuve speciale, alors qu'elle
    datait de la veille. `tout_charge` passe a True quand tous les types sont
    epuises.
    """

    hors_ligne = False
    date = None

    def __init__(self, ros, player):
        self.ros = ros
        self.nk_id = player.get("id")
        self.steam_id = next((p.get("id") for p in (player.get("platforms") or [])
                              if p.get("platform") == "steam"), None)
        self.courses = []
        self._pages = {type_epreuve: 1 for type_epreuve in TYPES}
        self._epuises = set()
        self._vus = set()

    @property
    def tout_charge(self):
        return len(self._epuises) >= len(TYPES)

    def page_suivante(self):
        """Lit une page de chaque type encore ouvert. Renvoie ce qui s'ajoute."""
        nouvelles = []
        for type_epreuve in TYPES:
            if type_epreuve in self._epuises:
                continue
            lot = self._lire_page(type_epreuve, self._pages[type_epreuve])
            if lot:
                self._pages[type_epreuve] += 1
                nouvelles.extend(lot)
            else:
                self._epuises.add(type_epreuve)

        if nouvelles:
            self.courses.extend(nouvelles)
            self.courses.sort(key=lambda c: c.date, reverse=True)
        self._garder()
        return nouvelles

    def _lire_page(self, type_epreuve, page):
        if page > PAGES_MAX:
            return []
        reponse = self.ros.fetch(
            f"api/v1/results?eventType={type_epreuve}&page={page}&take={PAR_PAGE}",
            method="GET")
        if not isinstance(reponse, list) or not reponse:
            return []

        identifiants = {e.get("eventId") for e in reponse}
        if identifiants <= self._vus:  # le backend rejoue la derniere page
            return []
        inedits = [e for e in reponse if e.get("eventId") not in self._vus]
        self._vus |= identifiants
        return [Course.depuis_evenement(e, self.nk_id, self.steam_id) for e in inedits]

    def _garder(self):
        """Met le cache a jour, sans jamais faire echouer un chargement."""
        try:
            cache.save_courses([c.en_cache() for c in self.courses])
        except OSError:
            pass


class ChargeurHorsLigne:
    """Sert les courses du dernier chargement, backend hors de portee.

    Les courses passees ne changent plus : les relire telles quelles est exact,
    a ceci pres qu'il peut en manquer de recentes.
    """

    hors_ligne = True

    def __init__(self, donnees):
        self.courses = [Course(c) for c in (donnees.get("courses") or [])]
        self.courses.sort(key=lambda c: c.date, reverse=True)
        self.date = donnees.get("fetchedAt")
        # Rien de plus a aller chercher : le bouton « charger la suite »
        # n'aurait aucun effet.
        self.tout_charge = True

    def page_suivante(self):
        return []


def ouvrir(ctx):
    """Chargeur en ligne si le backend repond, sinon repli sur le cache.

    Leve l'erreur d'origine seulement si aucune course n'a jamais ete chargee :
    il n'y a alors rien a montrer, et le message doit le dire.
    """
    try:
        return Chargeur(ctx.raceos, ctx.raceos.authenticate())
    except HubError:
        donnees = cache.load_courses()
        if not donnees or not donnees.get("courses"):
            raise
        return ChargeurHorsLigne(donnees)


def rapprocher(courses, variations):
    """Associe a chaque course la variation de rating qui l'englobe.

    Une variation couvre l'intervalle entre deux releves. Si plusieurs courses
    tombent dans le meme intervalle, l'ecart les concerne toutes ensemble : on
    le signale plutot que de le repartir au hasard.
    """
    for variation in variations:
        concernees = [c for c in courses
                      if variation.avant["date"] <= c.date <= variation.apres["date"]]
        for course in concernees:
            course.variation = variation
            course.variation_partagee = len(concernees)
    return courses


TOUS = "Tous"
RESULTATS = (TOUS, "Victoires", "Podiums", "Hors podium", "Abandons")


def valeurs(courses, attribut):
    """Valeurs distinctes d'un attribut, triees par frequence decroissante."""
    compte = {}
    for course in courses:
        valeur = getattr(course, attribut, "") or ""
        if valeur:
            compte[valeur] = compte.get(valeur, 0) + 1
    return [TOUS] + sorted(compte, key=lambda v: (-compte[v], v))


def filtrer(courses, epreuve=TOUS, circuit=TOUS, classe=TOUS, resultat=TOUS):
    """Applique les filtres de la barre d'outils."""
    def garde(course):
        if epreuve != TOUS and course.titre != epreuve:
            return False
        if circuit != TOUS and course.circuit != circuit:
            return False
        if classe != TOUS and course.classe != classe:
            return False
        if resultat == "Victoires":
            return course.victoire
        if resultat == "Podiums":
            return course.podium
        if resultat == "Hors podium":
            return not course.podium and not course.abandon
        if resultat == "Abandons":
            return course.abandon
        return True

    return [c for c in courses if garde(c)]
