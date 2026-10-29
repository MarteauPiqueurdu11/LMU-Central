"""Lecture des setups de Le Mans Ultimate, jeu ferme.

Le jeu range ses reglages dans `UserData/player/Settings/<circuit>/<nom>.svm`,
un fichier texte par setup. Chaque ligne y porte deux choses :

    RWSetting=6//4.50 deg
             ^   ^
             |   ce que le jeu affiche dans son garage
             l'indice interne

**L'indice ne veut rien dire hors de sa voiture** : le cran 6 est 4,50 deg sur
une GT3 et tout autre chose sur une hypercar. C'est donc le texte affiche qui
sert de valeur, ici comme a la comparaison.

Ce texte a deux defauts que le corpus revele :

- il est **traduit dans la langue du jeu au moment de l'enregistrement**. Un
  meme reglage s'ecrit `Off`, `Non`, `Aus` ou `Disattivato` selon la machine
  d'ou vient le setup. Compares tels quels, deux setups identiques semblent
  differer partout : d'ou `normaliser`.
- il vaut `N/A` — ou `N/D`, ou `N/V` — quand la voiture n'a pas ce reglage.
  Ces lignes-la sont ecartees : sur 167 cles, une bonne moitie ne concerne
  jamais la voiture qu'on regarde.
"""

import datetime
import os
import re
import unicodedata

from . import installation

EXTENSION = ".svm"

# `Cle=valeur//affichage`, l'affichage etant facultatif.
LIGNE = re.compile(r"^([A-Za-z0-9_]+)=([^/]*?)\s*(?://(.*))?$")
SECTION = re.compile(r"^\[([^\]]+)\]")
VEHICULE = re.compile(r"[\\/]Vehicles[\\/]([^\\/]+)", re.I)

# Le jeu ecrit les sauts de ligne des notes avec cet octet.
SEPARATEUR_NOTES = "\xff"

# Reglage que la voiture n'expose pas. `N/D` et `N/V` sont les traductions
# francaise et allemande de `N/A` : trois ecritures pour la meme absence.
ABSENTS = {"n/a", "n/d", "n/v", "non-adjustable", "fixed", ""}


# --- vocabulaire -----------------------------------------------------------
#
# On ne traduit que ce que le corpus prouve traduit : chaque entree ci-dessous
# a ete relevee sous plusieurs langues dans les fichiers reels, ou bien c'est
# un mot de structure sans ambiguite. Les noms propres (Standard, Sprint,
# Le Mans, Short, High Speed, RWD, Full...) restent tels que le jeu les ecrit :
# les traduire serait inventer.

MOTS = {
    "available": "Disponible", "disponible": "Disponible",
    "disponibile": "Disponible", "verfügbar": "Disponible",
    "off": "Non", "non": "Non", "aus": "Non", "disattivato": "Non",
    "race": "Course", "course": "Course", "gara": "Course", "rennen": "Course",
    "detached": "Détaché", "détaché": "Détaché",
    "abmontiert": "Détaché", "separata": "Détaché",
    # Le jeu emploie le meme adjectif pour une gomme et pour un amortisseur :
    # « 100% Soft » et « 0 (soft) » deviennent « 100% Tendre » et
    # « 0 (tendre) », exactement ce que sa traduction francaise affiche.
    "soft": "tendre", "tendre": "tendre", "morbida": "tendre", "weich": "tendre",
    "medium": "medium", "media": "medium", "mittel": "medium",
    "hard": "dur", "dur": "dur", "dura": "dur", "hart": "dur",
    "wet": "pluie", "mouillé": "pluie", "bagnato": "pluie", "nass": "pluie",
    # mots de structure, sans equivalent ambigu
    "open": "Ouvert", "closed": "Fermé",
    "disabled": "Désactivé", "linked": "Lié", "lowest": "minimum",
    "understeer": "sous-vireur", "oversteer": "survireur", "balanced": "équilibré",
}

# Traduites sans egard a la casse d'origine : `Grad` donne `deg`, pas `Deg`.
# Le litre s'ecrit tantot `103.0l`, tantot `104.0L`, dans les memes fichiers.
UNITES = {"grad": "deg", "lap": "tour", "laps": "tours", "runden": "tours",
          "l": "L"}

# Traduites d'un bloc, parce qu'elles tiennent en plusieurs mots.
EXPRESSIONS = {"no tape": "Sans adhésif"}

MOT = re.compile(r"[^\W\d_]+", re.UNICODE)


def _traduire(mot):
    """Traduit en gardant la casse d'origine : `Off` donne `Non`, `off` `non`."""
    unite = UNITES.get(mot.lower())
    if unite is not None:
        return unite
    cible = MOTS.get(mot.lower())
    if cible is None:
        return mot
    return cible[:1].upper() + cible[1:] if mot[:1].isupper() else cible


def normaliser(affiche):
    """Rend le texte du jeu dans une seule langue, ou "" s'il ne dit rien.

    Sans cela, comparer un setup enregistre en anglais a un setup enregistre
    en francais signalerait une difference sur chaque ligne a vocabulaire.
    """
    texte = (affiche or "").strip()
    if texte.lower() in ABSENTS:
        return ""
    for source, cible in EXPRESSIONS.items():
        if texte.lower() == source:
            return cible
    return MOT.sub(lambda m: _traduire(m.group(0)), texte)


# --- circuits et voitures --------------------------------------------------

CIRCUITS = {
    "bahrain": "Bahrain",
    "circuit de barcelona": "Barcelone",
    "circuit of the americas": "Austin (COTA)",
    "daytonarc": "Daytona (routier)",
    "fuji": "Fuji",
    "imola": "Imola",
    "interlagos": "Interlagos",
    "lagunaseca": "Laguna Seca",
    "lemans": "Le Mans",
    "monza": "Monza",
    "paulricard": "Paul Ricard",
    "portimao": "Portimão",
    "qatar": "Losail (Qatar)",
    "sebring": "Sebring",
    "showroom": "Showroom",
    "silverstone": "Silverstone",
    "silverstone_international": "Silverstone International",
    "silverstone_national": "Silverstone National",
    "silverstonewec": "Silverstone (WEC)",
    "spa": "Spa-Francorchamps",
}

# Seules les voitures dont le nom commercial est certain figurent ici ; pour
# les autres, `joli_nom` derive un libelle du dossier plutot que d'inventer.
VOITURES = {
    "911gt3r_2024": "Porsche 911 GT3 R LMGT3",
    "alpine_a424_2024": "Alpine A424",
    "aston_martin_valkyrie_2025": "Aston Martin Valkyrie",
    "aston_martin_vantage_amr_2023": "Aston Martin Vantage AMR GTE",
    "bmw_m4_lmgt3_2023": "BMW M4 LMGT3",
    "bmw_m_hybrid_v8_2023": "BMW M Hybrid V8",
    "cadillac_v-lmdh_2023": "Cadillac V-Series.R",
    "chevrolet_c8r_lm_2023": "Chevrolet Corvette C8.R",
    "ferrari_296gt3_2023": "Ferrari 296 LMGT3",
    "ferrari_488gte_lm_2023": "Ferrari 488 GTE",
    "ferrari_499p_2023": "Ferrari 499P",
    "ford_mustang_gt3_2024": "Ford Mustang LMGT3",
    "genesis_gmr001_2026": "Genesis GMR-001",
    "isotta_tipo6_2024": "Isotta Fraschini Tipo 6-C",
    "lamborghini_sc63_2024": "Lamborghini SC63",
    "lexusrcf_gt3_2024": "Lexus RC F LMGT3",
    "ligier_jsp325_2025": "Ligier JS P325",
    "mclaren_720sgt3evo_2023": "McLaren 720S LMGT3 Evo",
    "oreca_07_elms_2023": "Oreca 07 (ELMS)",
    "oreca_07_lm_2023": "Oreca 07 (Le Mans)",
    "peugeot_9x8_2023": "Peugeot 9X8 (2023)",
    "peugeot_9x8_2024": "Peugeot 9X8 (2024)",
    "porsche_911rsr-19_2023": "Porsche 911 RSR-19",
    "porsche_963_2023": "Porsche 963",
    "toyota_gr10_2023": "Toyota GR010 Hybrid",
    "vandervell_680_2023": "Vandervell 680",
}

# Jetons de `VehicleClassSetting` qui designent la categorie, pas le modele.
CATEGORIES = {
    "hypercar": "Hypercar", "gt3": "LMGT3", "gte": "GTE",
    "lmp2": "LMP2", "lmp2_elms": "LMP2", "lmp3": "LMP3",
}
SAISON = re.compile(r"^(WEC|ELMS|IMSA)(\d{4})$", re.I)
ANNEE_FINALE = re.compile(r"_(19|20)\d\d$")


def joli_circuit(dossier):
    connu = CIRCUITS.get(dossier.strip().lower())
    if connu:
        return connu
    return dossier.replace("_", " ").strip() or "?"


def joli_vehicule(dossier):
    """Nom lisible d'un dossier de voiture, sans rien inventer."""
    if not dossier:
        return "Voiture inconnue"
    connu = VOITURES.get(dossier.strip().lower())
    if connu:
        return connu
    return ANNEE_FINALE.sub("", dossier).replace("_", " ").strip() or dossier


def _sans_accents(texte):
    decompose = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in decompose if not unicodedata.combining(c))


# --- disposition des valeurs ----------------------------------------------
#
# Calquee sur le garage du jeu en francais : memes onglets, memes sections,
# memes libelles, dans le meme ordre. L'onglet Basique n'est pas repris, il ne
# fait que redire les autres. Les reglages qu'aucune voiture du corpus n'expose
# — donc absents des captures du garage — gardent un libelle descriptif et
# leur place la plus probable.
#
# `DISPOSITION` vaut `((onglet, groupes), ...)`, un groupe `(titre, entrees)`,
# une entree `(sources, libelle)`. Les sources sont :
#
#   ((section, cle),)                         une valeur seule
#   ((section_g, cle_g), (section_d, cle_d))  gauche et droite
#   (gauche, troisieme_element, droite)       les deux roues et le 3e ressort,
#                                             dans l'ordre des colonnes du jeu
#
# Une cle absente de cette table reste affichee, dans « Autres reglages » :
# une nouvelle voiture ne doit rien faire disparaitre.

AVANT = ("FRONTLEFT", "FRONTRIGHT")
ARRIERE = ("REARLEFT", "REARRIGHT")

GAUCHE, TROISIEME, DROITE = "À GAUCHE", "3E RESSORT", "DROITE"
# Gauche et droite repliees en une colonne, a cote du 3e ressort.
ROUES = "ROUES"


def _seul(section, cle, libelle):
    return (((section, cle),), libelle)


def _roue(essieu, cle, libelle):
    return (((essieu[0], cle), (essieu[1], cle)), libelle)


def _paire(gauche, droite, libelle):
    """Un reglage de la section SUSPENSION ecrit en deux cles, gauche et droite."""
    return ((("SUSPENSION", gauche), ("SUSPENSION", droite)), libelle)


def _trio(essieu, prefixe, cle, libelle):
    """Les deux roues d'un essieu et son troisieme element, comme au garage."""
    return (((essieu[0], f"{cle}Setting"),
             ("SUSPENSION", f"{prefixe}3rd{cle}Setting"),
             (essieu[1], f"{cle}Setting")), libelle)


def _roues(essieu):
    return (
        _roue(essieu, "CompoundSetting", "Gomme"),
        _roue(essieu, "PressureSetting", "Pression des pneus"),
        _roue(essieu, "CamberSetting", "Carrossage"),
        _roue(essieu, "BrakeDiscSetting", "Disque de frein"),
        _roue(essieu, "BrakePadSetting", "Plaquettes"),
    )


def _suspension(essieu, prefixe):
    return (
        _trio(essieu, prefixe, "Spring", "Compression de ressort"),
        _trio(essieu, prefixe, "TenderSpring", "Compression de ressort faible"),
        _trio(essieu, prefixe, "TenderTravel", "Course de ressort faible"),
        _trio(essieu, prefixe, "Packer", "Cales de réglage"),
        _roue(essieu, "RideHeightSetting", "Hauteur de caisse"),
        _roue(essieu, "SpringRubberSetting", "Cales de ressort"),
    )


def _amortisseurs(essieu, prefixe):
    return (
        _trio(essieu, prefixe, "SlowBump", "Amortissement lent"),
        _trio(essieu, prefixe, "SlowRebound", "Rebond lent"),
        _trio(essieu, prefixe, "FastBump", "Amortissement rapide"),
        _trio(essieu, prefixe, "FastRebound", "Rebond rapide"),
    )


RAPPORTS = ("1er", "2e", "3e", "4e", "5e", "6e", "7e")

DISPOSITION = (
    ("Groupe motopropulseur", (
        ("Moteur", (
            _seul("GENERAL", "VirtualEnergySetting", "Énergie virtuelle"),
            _seul("GENERAL", "FuelSetting", "Capacité en carburant"),
            _seul("GENERAL", "FuelCapacitySetting", "Carburant embarqué"),
            _seul("ENGINE", "RevLimitSetting", "Limiteur de régime"),
            _seul("ENGINE", "EngineMixtureSetting", "Mélange moteur"),
            _seul("ENGINE", "EngineBoostSetting", "Suralimentation"),
            _seul("ENGINE", "EngineBrakingMapSetting", "Frein moteur"),
            _seul("BODYAERO", "WaterRadiatorSetting", "Fermeture du radiateur d'eau"),
            _seul("BODYAERO", "OilRadiatorSetting", "Fermeture du radiateur d'huile"),
        )),
        ("Électronique", (
            _seul("CONTROLS", "TCSetting", "Antipatinage"),
            _seul("CONTROLS", "TractionControlMapSetting", "TC à bord"),
            _seul("CONTROLS", "TCPowerCutMapSetting", "TC Power cut"),
            _seul("CONTROLS", "TCSlipAngleMapSetting", "TC Slip Angle"),
            _seul("ENGINE", "RegenerationMapSetting", "Niveau de recharge"),
            _seul("ENGINE", "ElectricMotorMapSetting", "Cartographie moteur électrique"),
        )),
        ("Différentiel", (
            _seul("DRIVELINE", "DiffPowerSetting", "Puissance"),
            _seul("DRIVELINE", "DiffCoastSetting", "Coast"),
            _seul("DRIVELINE", "DiffPreloadSetting", "Précharge"),
            _seul("DRIVELINE", "DiffPumpSetting", "Pompe"),
            _seul("DRIVELINE", "FrontDiffPowerSetting", "Puissance avant"),
            _seul("DRIVELINE", "FrontDiffCoastSetting", "Coast avant"),
            _seul("DRIVELINE", "FrontDiffPreloadSetting", "Précharge avant"),
            _seul("DRIVELINE", "FrontDiffPumpSetting", "Pompe avant"),
            _seul("DRIVELINE", "RearSplitSetting", "Répartition du couple"),
        )),
        ("Passage de rapport", (
            _seul("DRIVELINE", "RatioSetSetting", "Plage de rapports"),
            _seul("DRIVELINE", "FinalDriveSetting", "Rapport final"),
            *(_seul("DRIVELINE", f"Gear{n}Setting", f"{nom} rapport")
              for n, nom in enumerate(RAPPORTS, start=1)),
            _seul("DRIVELINE", "ReverseSetting", "Marche arrière"),
            _seul("DRIVELINE", "GearAutoUpShiftSetting", "Montée automatique"),
            _seul("DRIVELINE", "GearAutoDownShiftSetting", "Rétrogradage automatique"),
        )),
    )),
    ("Roues et freins", (
        ("Roues avant", _roues(AVANT)),
        ("Roues arrière", _roues(ARRIERE)),
        ("Freins", (
            _seul("CONTROLS", "RearBrakeSetting", "Répartition des freins"),
            _seul("CONTROLS", "BrakeMigrationSetting", "Migration des freins"),
            _seul("CONTROLS", "BrakePressureSetting", "Résistance pédale max"),
            _seul("BODYAERO", "BrakeDuctSetting", "Refroidissement des freins avant"),
            _seul("BODYAERO", "BrakeDuctRearSetting", "Refroidissement des freins arrière"),
            _seul("CONTROLS", "ABSSetting", "ABS"),
            _seul("CONTROLS", "AntilockBrakeSystemMapSetting", "Cartographie ABS"),
            _seul("CONTROLS", "HandfrontbrakePressSetting", "Frein à main avant"),
            _seul("CONTROLS", "HandbrakePressSetting", "Frein à main"),
        )),
    )),
    ("Suspension", (
        ("Suspension avant", _suspension(AVANT, "Front")),
        ("Suspension arrière", _suspension(ARRIERE, "Rear")),
    )),
    # Le jeu reprend ici les titres de l'onglet Suspension.
    ("Amortisseurs", (
        ("Suspension avant", _amortisseurs(AVANT, "Front")),
        ("Suspension arrière", _amortisseurs(ARRIERE, "Rear")),
    )),
    ("Châssis et aérodynamisme", (
        ("Châssis avant", (
            _paire("LeftCasterSetting", "RightCasterSetting", "Angle de chasse"),
            _seul("SUSPENSION", "FrontToeInSetting", "Pincement"),
            _seul("SUSPENSION", "FrontToeOffsetSetting", "Décalage de pincement"),
            _seul("SUSPENSION", "FrontAntiSwaySetting", "Barre antiroulis"),
            _seul("SUSPENSION", "FrontWheelTrackSetting", "Roulement avant"),
            _seul("CONTROLS", "SteerLockSetting", "Limite du volant (blocage)"),
            _seul("FRONTWING", "FWSetting", "Diffuseur avant"),
            _paire("LeftTrackBarSetting", "RightTrackBarSetting", "Barre Panhard"),
            ((("LEFTFENDER", "FenderFlareSetting"), ("RIGHTFENDER", "FenderFlareSetting")),
             "Élargisseur d'aile"),
        )),
        ("Châssis arrière", (
            _seul("SUSPENSION", "RearToeInSetting", "Pincement"),
            _seul("SUSPENSION", "RearToeOffsetSetting", "Décalage de pincement"),
            _seul("SUSPENSION", "RearAntiSwaySetting", "Barre antiroulis"),
            _seul("SUSPENSION", "RearWheelTrackSetting", "Roulement arrière"),
            _seul("REARWING", "RWSetting", "Aileron arrière"),
        )),
        ("Poids", (
            _seul("GENERAL", "CGHeightSetting", "Verticale"),
            _seul("GENERAL", "CGRightSetting", "Latérale"),
            _seul("GENERAL", "CGRearSetting", "Répartition du poids"),
            _seul("GENERAL", "WedgeSetting", "Biais de suspension"),
        )),
        ("Châssis avancé", tuple(
            _seul("SUSPENSION", f"ChassisAdj{n:02d}Setting", f"Ajustement du châssis {n}")
            for n in range(12))),
    )),
    ("Hors garage", (
        # La strategie d'arrets enregistree avec le setup.
        ("Arrêts au stand", (
            _seul("GENERAL", "NumPitstopsSetting", "Arrêts prévus"),
            *(_seul("GENERAL", f"Pitstop{n}Setting", f"Arrêt {n}") for n in (1, 2, 3)),
        )),
    )),
)

# Toutes les cles qui ont leur place ci-dessus, affichees ou non.
RANGEES = {source for _, groupes in DISPOSITION for _, entrees in groupes
           for sources, _ in entrees for source in sources}

ONGLET_AUTRES = "Hors garage"
TITRE_AUTRES = "Autres réglages"

# Reglages qui n'ont de sens qu'en presence d'un autre. `FuelSetting` est la
# capacite en carburant des voitures a energie virtuelle, en fraction du
# reservoir ; sur celles qui se remplissent en litres, il redit la charge
# divisee par cent (`0.88` pour `88.0L`), deja lue dans « Carburant embarque ».
CONDITIONNELLES = {("GENERAL", "FuelSetting"): ("GENERAL", "VirtualEnergySetting")}

# Lues a part : ce sont des informations sur le fichier, pas des reglages.
META = {("", "VehicleClassSetting"), ("", "UpgradeSetting"),
        ("GENERAL", "Notes"), ("GENERAL", "Symmetric"),
        ("BASIC", "Downforce"), ("BASIC", "Balance"), ("BASIC", "Ride"),
        ("BASIC", "Gearing"), ("BASIC", "Custom")}


def _entrees():
    """Toutes les entrees, a plat, avec leur onglet et leur groupe."""
    for onglet, groupes in DISPOSITION:
        for titre, entrees in groupes:
            yield onglet, titre, entrees


def _visible(setup, source):
    """Vrai si la source a sa place dans ce setup."""
    condition = CONDITIONNELLES.get(source)
    return condition is None or bool(setup.affiche(*condition))


def _valeurs(setup, sources):
    """Les valeurs affichables d'une entree, "" la ou il n'y a rien a montrer."""
    return [setup.affiche(*source) if _visible(setup, source) else ""
            for source in sources]


def _cotes_egaux(sources, valeurs):
    """Vrai si gauche et droite portent le meme reglage, ou s'il n'y a pas de cotes.

    La gauche est toujours la premiere source, la droite la derniere : le 3e
    ressort, au milieu, n'a pas de cote.
    """
    if len(sources) == 1:
        return True
    return _noyau(sources[0][1], valeurs[0]) == _noyau(sources[-1][1], valeurs[-1])


def _colonnes(separes, troisieme):
    if troisieme:
        return (GAUCHE, TROISIEME, DROITE) if separes else (ROUES, TROISIEME)
    return (GAUCHE, DROITE) if separes else ()


def _ranger(valeurs, separes, troisieme):
    """Place les valeurs d'une entree sous les colonnes de son groupe.

    None marque une case vide — la hauteur de caisse n'a pas de 3e ressort —
    a distinguer de "", un reglage que la voiture n'a pas.
    """
    if len(valeurs) == 1:
        return valeurs
    gauche, droite = valeurs[0], valeurs[-1]
    centre = valeurs[1] if len(valeurs) == 3 else None
    roues = [gauche, droite] if separes else [gauche or droite]
    if troisieme:
        roues.insert(1, centre)
    return roues


class Ligne:
    """Un reglage pret a afficher : un libelle, une a trois valeurs."""

    def __init__(self, libelle, valeurs, sources=None):
        self.libelle = libelle
        self.valeurs = valeurs      # une par colonne du groupe ; None : case vide
        self.sources = sources      # les (section, cle) d'origine

    @property
    def valeur(self):
        return self.valeurs[0]

    def __repr__(self):
        return f"<Ligne {self.libelle}={self.valeurs}>"


class Setup:
    """Un fichier .svm lu et mis en forme."""

    def __init__(self, chemin, valeurs, meta, modifie):
        self.chemin = chemin
        self.nom = chemin.stem
        self.dossier_circuit = chemin.parent.name
        self.circuit = joli_circuit(self.dossier_circuit)
        self.valeurs = valeurs          # (section, cle) -> (brut, affiche)
        self.modifie = modifie

        self.dossier_voiture = meta.get("vehicule") or ""
        self.voiture = joli_vehicule(self.dossier_voiture)
        self.categorie = meta.get("categorie") or ""
        self.saison = meta.get("saison") or ""
        self.notes = meta.get("notes") or ""
        self.symetrique = self._est_symetrique()

    # --- acces ---

    def affiche(self, section, cle):
        """Valeur affichable, ou "" si la voiture n'a pas ce reglage."""
        return (self.valeurs.get((section, cle)) or ("", ""))[1]

    def brut(self, section, cle):
        return (self.valeurs.get((section, cle)) or ("", ""))[0]

    @property
    def gomme(self):
        return self.affiche("FRONTLEFT", "CompoundSetting")

    @property
    def carburant(self):
        return self.affiche("GENERAL", "FuelCapacitySetting")

    @property
    def sous_la_pluie(self):
        return self.gomme.lower().endswith("pluie")

    def _est_symetrique(self):
        """Vrai si gauche et droite portent partout le meme reglage."""
        return all(_cotes_egaux(sources, _valeurs(self, sources))
                   for _, _, entrees in _entrees() for sources, _ in entrees)

    # --- mise en forme ---

    def groupes(self):
        """Les reglages renseignes, groupes et ordonnes comme dans le garage.

        Rend une suite de `(onglet, titre, colonnes, lignes)`. Un groupe ne
        separe gauche et droite que si l'un de ses reglages differe d'un cote
        a l'autre — l'usure du pneu et l'estimation en tours ne comptent pas —
        et ne prend la colonne du 3e ressort que si la voiture en a un.
        `colonnes` est vide quand chaque ligne n'a qu'une valeur.
        """
        blocs = []
        for onglet, titre, entrees in _entrees():
            rangees = [(sources, libelle, _valeurs(self, sources))
                       for sources, libelle in entrees]
            rangees = [r for r in rangees if any(r[2])]
            if not rangees:
                continue
            separes = not all(_cotes_egaux(sources, valeurs)
                              for sources, _, valeurs in rangees)
            troisieme = any(len(valeurs) == 3 and valeurs[1]
                            for _, _, valeurs in rangees)
            lignes = [Ligne(libelle, _ranger(valeurs, separes, troisieme), sources)
                      for sources, libelle, valeurs in rangees]
            blocs.append((onglet, titre, _colonnes(separes, troisieme), lignes))

        vus = RANGEES | META
        autres = [Ligne(cle, [self.affiche(section, cle)], ((section, cle),))
                  for (section, cle) in sorted(self.valeurs)
                  if (section, cle) not in vus and self.affiche(section, cle)]
        if autres:
            blocs.append((ONGLET_AUTRES, TITRE_AUTRES, (), autres))
        return blocs

    def __repr__(self):
        return f"<Setup {self.circuit} / {self.voiture} / {self.nom}>"


# --- lecture ---------------------------------------------------------------

def _texte(chemin):
    """Le contenu du fichier, quelle que soit la langue du jeu qui l'a ecrit.

    Deux setups sur les quatre cent quarante du corpus d'essai sont en cp1252,
    pas en UTF-8 : lus sans precaution, leur angle de braquage devient
    `516� (19.7�)` au lieu de `516° (19.7°)`.
    """
    octets = chemin.read_bytes()
    try:
        return octets.decode("utf-8")
    except UnicodeDecodeError:
        return octets.decode("cp1252", errors="replace")


def _classer(classes, vehicule):
    """Tire la categorie et la saison de `VehicleClassSetting`.

    Ses jetons ne sont pas ordonnes : `"Ferrari_296_LMGT3 GT3 WEC2025"` et
    `"GT3 Lexus_RCF_GT3 WEC2025"` decrivent la meme chose dans un autre ordre.
    On reconnait donc chaque jeton par ce qu'il est, pas par sa place.
    """
    categorie = saison = ""
    modele = ""
    for jeton in classes.split():
        connue = CATEGORIES.get(jeton.lower())
        if connue:
            categorie = categorie or connue
            continue
        m = SAISON.match(jeton)
        if m:
            saison = saison or f"{m.group(1).upper()} {m.group(2)}"
            continue
        modele = modele or jeton
    return categorie, saison, modele


def _vehicule_de_secours(modele):
    """Retrouve le dossier de la voiture quand la ligne `//VEH=` manque.

    Elle manque sur les setups distribues hors du jeu. Le jeton restant de
    `VehicleClassSetting` — `Isotta_TIPO6` — designe alors le meme modele que
    le dossier `Isotta_Tipo6_2024`, a la casse et a l'annee pres.
    """
    if not modele:
        return ""
    reference = _sans_accents(modele).lower().replace("-", "_")
    for dossier in VOITURES:
        allege = ANNEE_FINALE.sub("", dossier).replace("-", "_")
        if allege == reference:
            return dossier
    return ""


def lire(chemin):
    """Lit un fichier .svm et rend un `Setup`."""
    valeurs, meta = {}, {}
    section = ""
    classes = ""

    for ligne in _texte(chemin).splitlines():
        ligne = ligne.strip()
        if not ligne:
            continue
        if ligne.startswith("//"):
            trouve = VEHICULE.search(ligne)
            if trouve:
                meta["vehicule"] = trouve.group(1)
            continue
        entete = SECTION.match(ligne)
        if entete:
            section = entete.group(1).upper()
            continue
        m = LIGNE.match(ligne)
        if not m:
            continue
        cle, brut, affiche = m.group(1), m.group(2).strip(), m.group(3)
        if cle == "VehicleClassSetting":
            classes = brut.strip('"')
        elif cle == "Notes":
            meta["notes"] = brut.strip('"').replace(SEPARATEUR_NOTES, "\n").strip()
        valeurs[(section, cle)] = (brut, normaliser(affiche))

    meta["categorie"], meta["saison"], modele = _classer(classes, meta.get("vehicule"))
    if not meta.get("vehicule"):
        meta["vehicule"] = _vehicule_de_secours(modele)

    horodatage = datetime.datetime.fromtimestamp(chemin.stat().st_mtime)
    return Setup(chemin, valeurs, meta, horodatage)


# Les trois axes par lesquels on trie une collection. Les nommer une fois
# evite de repeter la meme cascade de `if` dans le filtrage, le decompte et le
# regroupement.
CRITERES = {
    "circuit": lambda s: s.circuit,
    "voiture": lambda s: s.voiture,
    "categorie": lambda s: s.categorie,
}


class Collection:
    """Tous les setups trouves sur le disque, et de quoi s'y retrouver."""

    def __init__(self, setups, dossier, illisibles=()):
        self.setups = setups
        self.dossier = dossier
        self.illisibles = list(illisibles)

    def __len__(self):
        return len(self.setups)

    def valeurs(self, critere, parmi=None):
        """Les valeurs prises par un critere, et leur compte, par ordre alphabetique.

        `parmi` restreint le decompte a un sous-ensemble : c'est ce qui permet
        a un menu de ne proposer que ce qui reste atteignable compte tenu des
        autres filtres.
        """
        lire = CRITERES[critere]
        compte = {}
        for setup in (self.setups if parmi is None else parmi):
            valeur = lire(setup)
            if valeur:
                compte[valeur] = compte.get(valeur, 0) + 1
        return sorted(compte.items(), key=lambda kv: _sans_accents(kv[0]).lower())

    def circuits(self, parmi=None):
        return self.valeurs("circuit", parmi)

    def voitures(self, parmi=None):
        return self.valeurs("voiture", parmi)

    def categories(self, parmi=None):
        return self.valeurs("categorie", parmi)

    def filtrer(self, circuit=None, voiture=None, categorie=None, recherche=""):
        """Le sous-ensemble correspondant aux filtres, dans l'ordre d'affichage."""
        mots = [m for m in _sans_accents(recherche).lower().split() if m]
        voulus = {"circuit": circuit, "voiture": voiture, "categorie": categorie}
        retenus = []
        for setup in self.setups:
            if any(valeur and CRITERES[critere](setup) != valeur
                   for critere, valeur in voulus.items()):
                continue
            if mots:
                cible = _sans_accents(
                    f"{setup.nom} {setup.voiture} {setup.circuit} {setup.notes}").lower()
                if not all(mot in cible for mot in mots):
                    continue
            retenus.append(setup)
        return retenus


def charger(dossier=None):
    """Lit tous les setups presents sur le disque.

    Un fichier illisible n'interrompt pas le reste : il est signale a part.
    """
    racine = dossier or installation.dossier_setups()
    setups, illisibles = [], []
    for chemin in sorted(racine.glob(f"*/*{EXTENSION}"),
                         key=lambda p: (p.parent.name.lower(), p.stem.lower())):
        try:
            setups.append(lire(chemin))
        except OSError as exc:
            illisibles.append((chemin, str(exc)))
    setups.sort(key=lambda s: (s.circuit.lower(), s.voiture.lower(), s.nom.lower()))
    return Collection(setups, racine, illisibles)


# --- comparaison -----------------------------------------------------------

# Deux reglages annoncent, entre parentheses, l'autonomie que le jeu en deduit.
# Elle depend du circuit et de la voiture, pas du reglage : deux setups a 100%
# d'energie virtuelle ne different pas parce que l'un promet 32,2 tours et
# l'autre 32,3.
ESTIMATIONS = {"VirtualEnergySetting", "FuelCapacitySetting"}
PARENTHESE = re.compile(r"\s*\([^)]*\)\s*$")

# La gomme, elle, se prefixe de son usure au moment de l'enregistrement —
# `94% Medium`. C'est un etat, pas un choix : un train use a 94% a gauche et a
# 96% a droite ne fait pas un setup asymetrique.
CLE_GOMME = "CompoundSetting"
USURE = re.compile(r"^\d+\s*%\s*")


def _noyau(cle, texte):
    """La part du texte qui constitue vraiment le reglage."""
    if cle in ESTIMATIONS:
        return PARENTHESE.sub("", texte)
    if cle == CLE_GOMME:
        return USURE.sub("", texte)
    return texte


class Ecart:
    """Une ligne de comparaison : le meme reglage dans les deux setups."""

    def __init__(self, libelle, gauche, droite, cle=None):
        self.libelle = libelle
        self.gauche = gauche
        self.droite = droite
        self.cle = cle

    @property
    def different(self):
        cle = self.cle[1] if self.cle else None
        return _noyau(cle, self.gauche) != _noyau(cle, self.droite)

    def __repr__(self):
        marque = "≠" if self.different else "="
        return f"<Ecart {self.libelle} {self.gauche!r} {marque} {self.droite!r}>"


ABSENT = "—"


def comparer(gauche, droite):
    """Confronte deux setups, groupe par groupe, dans l'ordre du garage.

    Rend `[(onglet, titre, [Ecart, ...]), ...]`. Les roues d'un reglage
    tiennent en une ligne si leurs deux cotes se repondent dans l'un et
    l'autre setup ; sinon elles en donnent deux, « · gauche » et « · droite » :
    replier masquerait justement l'asymetrie qu'on cherche a voir. Le 3e
    ressort a toujours sa ligne a lui.

    La comparaison porte sur le texte normalise, jamais sur l'indice interne :
    le cran 6 ne designe pas le meme angle d'aileron d'une voiture a l'autre.
    """
    blocs = []
    for onglet, titre, entrees in _entrees():
        ecarts = []
        for sources, libelle in entrees:
            a, b = _valeurs(gauche, sources), _valeurs(droite, sources)
            ecarts.extend(_ecarts(sources, libelle, a, b))
        if ecarts:
            blocs.append((onglet, titre, ecarts))

    vus = RANGEES | META
    autres = []
    for section, cle in sorted(set(gauche.valeurs) | set(droite.valeurs)):
        if (section, cle) in vus:
            continue
        a, b = gauche.affiche(section, cle), droite.affiche(section, cle)
        if a or b:
            autres.append(Ecart(cle, a or ABSENT, b or ABSENT, (section, cle)))
    if autres:
        blocs.append((ONGLET_AUTRES, TITRE_AUTRES, autres))
    return blocs


def _ecarts(sources, libelle, a, b):
    """Les lignes de comparaison d'une entree, dans l'ordre des colonnes du jeu."""
    if len(sources) == 1:
        return [Ecart(libelle, a[0] or ABSENT, b[0] or ABSENT, sources[0])] \
            if a[0] or b[0] else []

    if _cotes_egaux(sources, a) and _cotes_egaux(sources, b):
        cotes = [(libelle, 0, a[0] or a[-1], b[0] or b[-1])]
    else:
        cotes = [(f"{libelle} · gauche", 0, a[0], b[0]),
                 (f"{libelle} · droite", len(sources) - 1, a[-1], b[-1])]
    if len(sources) == 3:
        cotes.insert(1, (f"{libelle} · 3e ressort", 1, a[1], b[1]))

    return [Ecart(nom, va or ABSENT, vb or ABSENT, sources[indice])
            for nom, indice, va, vb in cotes if va or vb]


def resumer(blocs):
    """Nombre de lignes comparees, et nombre de lignes qui different."""
    lignes = [e for _, _, ecarts in blocs for e in ecarts]
    return len(lignes), sum(1 for e in lignes if e.different)


def exporter(setup):
    """Le setup en texte brut, pret a etre copie dans un message."""
    lignes = [f"{setup.nom}",
              f"{setup.voiture} · {setup.circuit}"
              + (f" · {setup.categorie}" if setup.categorie else ""),
              f"modifié le {setup.modifie:%d/%m/%Y à %H:%M}"]
    if setup.notes:
        lignes.append(setup.notes.replace("\n", " · "))
    onglet_courant = None
    for onglet, titre, colonnes, contenu in setup.groupes():
        if onglet != onglet_courant:
            lignes += ["", f"=== {onglet.upper()} ==="]
            onglet_courant = onglet
        lignes.append("")
        lignes.append(titre.upper())
        if colonnes:
            lignes.append(f"  {'':<36}" + "".join(f"{c:<22}" for c in colonnes).rstrip())
        for ligne in contenu:
            valeurs = "".join(f"{v or '':<22}" for v in ligne.valeurs)
            lignes.append(f"  {ligne.libelle:<36}{valeurs}".rstrip())
    return os.linesep.join(lignes)
