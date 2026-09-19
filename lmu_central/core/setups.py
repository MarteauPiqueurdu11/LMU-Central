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
# L'ordre suit celui du garage du jeu : ce qu'on regle en premier vient en
# premier. Une cle absente de ces tables reste affichee, dans un groupe
# « Autres reglages » : une nouvelle voiture ne doit rien faire disparaitre.

COINS = ("FRONTLEFT", "FRONTRIGHT", "REARLEFT", "REARRIGHT")
NOMS_COINS = ("AV G", "AV D", "AR G", "AR D")
NOMS_ESSIEUX = ("AVANT", "ARRIÈRE")

GROUPES = (
    ("Général", (
        ("GENERAL", "FuelCapacitySetting", "Carburant"),
        ("GENERAL", "VirtualEnergySetting", "Énergie virtuelle"),
        ("GENERAL", "NumPitstopsSetting", "Arrêts prévus"),
        ("GENERAL", "Pitstop1Setting", "Arrêt 1"),
        ("GENERAL", "Pitstop2Setting", "Arrêt 2"),
        ("GENERAL", "Pitstop3Setting", "Arrêt 3"),
        ("GENERAL", "WedgeSetting", "Biais de suspension"),
    )),
    ("Aérodynamique et refroidissement", (
        ("FRONTWING", "FWSetting", "Aileron avant"),
        ("REARWING", "RWSetting", "Aileron arrière"),
        ("LEFTFENDER", "FenderFlareSetting", "Élargisseur d'aile gauche"),
        ("RIGHTFENDER", "FenderFlareSetting", "Élargisseur d'aile droite"),
        ("BODYAERO", "WaterRadiatorSetting", "Radiateur d'eau"),
        ("BODYAERO", "OilRadiatorSetting", "Radiateur d'huile"),
        ("BODYAERO", "BrakeDuctSetting", "Écopes de frein avant"),
        ("BODYAERO", "BrakeDuctRearSetting", "Écopes de frein arrière"),
    )),
    ("Freinage et direction", (
        ("CONTROLS", "SteerLockSetting", "Angle de braquage"),
        ("CONTROLS", "RearBrakeSetting", "Répartition de freinage"),
        ("CONTROLS", "BrakeMigrationSetting", "Migration de freinage"),
        ("CONTROLS", "BrakePressureSetting", "Pression de freinage"),
        ("CONTROLS", "HandfrontbrakePressSetting", "Frein à main avant"),
        ("CONTROLS", "HandbrakePressSetting", "Frein à main"),
        ("CONTROLS", "TCSetting", "Antipatinage"),
        ("CONTROLS", "TractionControlMapSetting", "Cartographie antipatinage"),
        ("CONTROLS", "TCPowerCutMapSetting", "Coupure moteur (TC)"),
        ("CONTROLS", "TCSlipAngleMapSetting", "Angle de glisse (TC)"),
        ("CONTROLS", "ABSSetting", "ABS"),
        ("CONTROLS", "AntilockBrakeSystemMapSetting", "Cartographie ABS"),
    )),
    ("Moteur", (
        ("ENGINE", "RevLimitSetting", "Limiteur"),
        ("ENGINE", "EngineMixtureSetting", "Mélange"),
        ("ENGINE", "EngineBoostSetting", "Suralimentation"),
        ("ENGINE", "EngineBrakingMapSetting", "Frein moteur"),
        ("ENGINE", "RegenerationMapSetting", "Récupération"),
        ("ENGINE", "ElectricMotorMapSetting", "Moteur électrique"),
    )),
    ("Transmission", (
        ("DRIVELINE", "RatioSetSetting", "Jeu de rapports"),
        ("DRIVELINE", "FinalDriveSetting", "Couple final"),
        ("DRIVELINE", "Gear1Setting", "1er rapport"),
        ("DRIVELINE", "Gear2Setting", "2e rapport"),
        ("DRIVELINE", "Gear3Setting", "3e rapport"),
        ("DRIVELINE", "Gear4Setting", "4e rapport"),
        ("DRIVELINE", "Gear5Setting", "5e rapport"),
        ("DRIVELINE", "Gear6Setting", "6e rapport"),
        ("DRIVELINE", "Gear7Setting", "7e rapport"),
        ("DRIVELINE", "ReverseSetting", "Marche arrière"),
        ("DRIVELINE", "RearSplitSetting", "Répartition du couple"),
        ("DRIVELINE", "DiffPowerSetting", "Différentiel — accélération"),
        ("DRIVELINE", "DiffCoastSetting", "Différentiel — décélération"),
        ("DRIVELINE", "DiffPreloadSetting", "Différentiel — précharge"),
        ("DRIVELINE", "DiffPumpSetting", "Différentiel — pompe"),
        ("DRIVELINE", "FrontDiffPowerSetting", "Diff. avant — accélération"),
        ("DRIVELINE", "FrontDiffCoastSetting", "Diff. avant — décélération"),
        ("DRIVELINE", "FrontDiffPreloadSetting", "Diff. avant — précharge"),
        ("DRIVELINE", "FrontDiffPumpSetting", "Diff. avant — pompe"),
        ("DRIVELINE", "GearAutoUpShiftSetting", "Montée automatique"),
        ("DRIVELINE", "GearAutoDownShiftSetting", "Rétrogradage automatique"),
    )),
    ("Liaison au sol", (
        ("SUSPENSION", "FrontAntiSwaySetting", "Barre antiroulis avant"),
        ("SUSPENSION", "RearAntiSwaySetting", "Barre antiroulis arrière"),
        ("SUSPENSION", "FrontToeInSetting", "Pincement avant"),
        ("SUSPENSION", "RearToeInSetting", "Pincement arrière"),
        ("SUSPENSION", "FrontToeOffsetSetting", "Décalage de pincement avant"),
        ("SUSPENSION", "RearToeOffsetSetting", "Décalage de pincement arrière"),
        ("SUSPENSION", "LeftCasterSetting", "Chasse gauche"),
        ("SUSPENSION", "RightCasterSetting", "Chasse droite"),
        ("SUSPENSION", "FrontWheelTrackSetting", "Voie avant"),
        ("SUSPENSION", "RearWheelTrackSetting", "Voie arrière"),
        ("SUSPENSION", "LeftTrackBarSetting", "Barre Panhard gauche"),
        ("SUSPENSION", "RightTrackBarSetting", "Barre Panhard droite"),
    )),
    ("Troisième élément", (
        ("SUSPENSION", "Front3rdSpringSetting", "Avant — ressort"),
        ("SUSPENSION", "Front3rdPackerSetting", "Avant — butée"),
        ("SUSPENSION", "Front3rdSlowBumpSetting", "Avant — compression lente"),
        ("SUSPENSION", "Front3rdFastBumpSetting", "Avant — compression rapide"),
        ("SUSPENSION", "Front3rdSlowReboundSetting", "Avant — détente lente"),
        ("SUSPENSION", "Front3rdFastReboundSetting", "Avant — détente rapide"),
        ("SUSPENSION", "Front3rdTenderSpringSetting", "Avant — ressort auxiliaire"),
        ("SUSPENSION", "Front3rdTenderTravelSetting", "Avant — course auxiliaire"),
        ("SUSPENSION", "Rear3rdSpringSetting", "Arrière — ressort"),
        ("SUSPENSION", "Rear3rdPackerSetting", "Arrière — butée"),
        ("SUSPENSION", "Rear3rdSlowBumpSetting", "Arrière — compression lente"),
        ("SUSPENSION", "Rear3rdFastBumpSetting", "Arrière — compression rapide"),
        ("SUSPENSION", "Rear3rdSlowReboundSetting", "Arrière — détente lente"),
        ("SUSPENSION", "Rear3rdFastReboundSetting", "Arrière — détente rapide"),
        ("SUSPENSION", "Rear3rdTenderSpringSetting", "Arrière — ressort auxiliaire"),
        ("SUSPENSION", "Rear3rdTenderTravelSetting", "Arrière — course auxiliaire"),
    )),
)

# Le meme ordre pour les quatre roues, presentees cote a cote.
ROUES = (
    ("CompoundSetting", "Gomme"),
    ("PressureSetting", "Pression"),
    ("CamberSetting", "Carrossage"),
    ("RideHeightSetting", "Hauteur de caisse"),
    ("SpringSetting", "Ressort"),
    ("PackerSetting", "Butée"),
    ("SlowBumpSetting", "Compression lente"),
    ("FastBumpSetting", "Compression rapide"),
    ("SlowReboundSetting", "Détente lente"),
    ("FastReboundSetting", "Détente rapide"),
    ("TenderSpringSetting", "Ressort auxiliaire"),
    ("TenderTravelSetting", "Course auxiliaire"),
    ("SpringRubberSetting", "Cale de ressort"),
    ("BrakeDiscSetting", "Disque de frein"),
    ("BrakePadSetting", "Plaquettes"),
)

TITRE_ROUES = "Roues"
TITRE_AUTRES = "Autres réglages"

# `FuelSetting` redit `FuelCapacitySetting` : la meme charge, divisee par cent
# (`0.88` pour `88.0L`) sur les voitures qui se remplissent en litres, et
# bloquee a `1.00` sur celles qui se remplissent en energie virtuelle. La
# ligne « Carburant » suffit, et elle porte en plus l'estimation en tours.
IGNOREES = {("GENERAL", "FuelSetting")}

# Lues a part : ce sont des informations sur le fichier, pas des reglages.
META = {("", "VehicleClassSetting"), ("", "UpgradeSetting"),
        ("GENERAL", "Notes"), ("GENERAL", "Symmetric"),
        ("BASIC", "Downforce"), ("BASIC", "Balance"), ("BASIC", "Ride"),
        ("BASIC", "Gearing"), ("BASIC", "Custom")}


class Ligne:
    """Un reglage pret a afficher : un libelle, une ou quatre valeurs."""

    def __init__(self, libelle, valeurs, cle=None):
        self.libelle = libelle
        self.valeurs = valeurs      # liste, de longueur 1, 2 ou 4
        self.cle = cle              # (section, cle) d'origine, pour la comparaison

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
        """Vrai si gauche et droite portent partout la meme valeur.

        C'est le cas courant, et cela permet de presenter deux colonnes —
        avant, arriere — au lieu de quatre.
        """
        for cle, _ in ROUES:
            cote = [_noyau(cle, self.affiche(coin, cle)) for coin in COINS]
            if cote[0] != cote[1] or cote[2] != cote[3]:
                return False
        return True

    # --- mise en forme ---

    def groupes(self):
        """Les reglages renseignes, groupes et ordonnes comme dans le garage.

        Rend une suite de `(titre, colonnes, lignes)`. `colonnes` est vide
        pour un groupe ordinaire, et porte les intitules des roues sinon.
        """
        vus = set(IGNOREES) | set(META)
        blocs = []

        for titre, entrees in GROUPES:
            lignes = []
            for section, cle, libelle in entrees:
                vus.add((section, cle))
                valeur = self.affiche(section, cle)
                if valeur:
                    lignes.append(Ligne(libelle, [valeur], (section, cle)))
            if lignes:
                blocs.append((titre, (), lignes))

        roues = self._bloc_roues(vus)
        if roues:
            blocs.append(roues)

        autres = [Ligne(cle, [self.affiche(section, cle)], (section, cle))
                  for (section, cle) in sorted(self.valeurs)
                  if (section, cle) not in vus and self.affiche(section, cle)]
        if autres:
            blocs.append((TITRE_AUTRES, (), autres))
        return blocs

    def _bloc_roues(self, vus):
        coins = COINS[::2] if self.symetrique else COINS
        entetes = NOMS_ESSIEUX if self.symetrique else NOMS_COINS
        lignes = []
        for cle, libelle in ROUES:
            for coin in COINS:
                vus.add((coin, cle))
            valeurs = [self.affiche(coin, cle) for coin in coins]
            if any(valeurs):
                lignes.append(Ligne(libelle, valeurs, ("ROUES", cle)))
        return (TITRE_ROUES, entetes, lignes) if lignes else None

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
    """Confronte deux setups, groupe par groupe.

    Rend `[(titre, [Ecart, ...]), ...]`. Les roues sont deroulees en lignes
    plutot qu'en colonnes : deux setups cote a cote donneraient huit colonnes,
    illisibles des que la fenetre retrecit.

    La comparaison porte sur le texte normalise, jamais sur l'indice interne :
    le cran 6 ne designe pas le meme angle d'aileron d'une voiture a l'autre.
    """
    vus = set(IGNOREES) | set(META)
    blocs = []

    for titre, entrees in GROUPES:
        ecarts = []
        for section, cle, libelle in entrees:
            vus.add((section, cle))
            a, b = gauche.affiche(section, cle), droite.affiche(section, cle)
            if a or b:
                ecarts.append(Ecart(libelle, a or ABSENT, b or ABSENT, (section, cle)))
        if ecarts:
            blocs.append((titre, ecarts))

    roues = _comparer_roues(gauche, droite, vus)
    if roues:
        blocs.append((TITRE_ROUES, roues))

    restantes = sorted(set(gauche.valeurs) | set(droite.valeurs))
    autres = []
    for section, cle in restantes:
        if (section, cle) in vus:
            continue
        a, b = gauche.affiche(section, cle), droite.affiche(section, cle)
        if a or b:
            autres.append(Ecart(cle, a or ABSENT, b or ABSENT, (section, cle)))
    if autres:
        blocs.append((TITRE_AUTRES, autres))
    return blocs


def _comparer_roues(gauche, droite, vus):
    """Deroule les quatre roues, en repliant les cotes qui se repondent.

    Si les deux setups sont symetriques sur un reglage, deux lignes suffisent
    — avant, arriere. Sinon les quatre sont montrees : replier masquerait
    justement l'asymetrie qu'on cherche a voir.
    """
    ecarts = []
    for cle, libelle in ROUES:
        for coin in COINS:
            vus.add((coin, cle))
        valeurs = {coin: (gauche.affiche(coin, cle), droite.affiche(coin, cle))
                   for coin in COINS}
        if not any(a or b for a, b in valeurs.values()):
            continue
        cotes = {coin: tuple(_noyau(cle, texte) for texte in paire)
                 for coin, paire in valeurs.items()}
        symetrique = (cotes["FRONTLEFT"] == cotes["FRONTRIGHT"]
                      and cotes["REARLEFT"] == cotes["REARRIGHT"])
        coins = COINS[::2] if symetrique else COINS
        noms = NOMS_ESSIEUX if symetrique else NOMS_COINS
        for coin, nom in zip(coins, noms):
            a, b = valeurs[coin]
            ecarts.append(Ecart(f"{libelle} · {nom}", a or ABSENT, b or ABSENT,
                                (coin, cle)))
    return ecarts


def resumer(blocs):
    """Nombre de lignes comparees, et nombre de lignes qui different."""
    lignes = [e for _, ecarts in blocs for e in ecarts]
    return len(lignes), sum(1 for e in lignes if e.different)


def exporter(setup):
    """Le setup en texte brut, pret a etre copie dans un message."""
    lignes = [f"{setup.nom}",
              f"{setup.voiture} · {setup.circuit}"
              + (f" · {setup.categorie}" if setup.categorie else ""),
              f"modifié le {setup.modifie:%d/%m/%Y à %H:%M}"]
    if setup.notes:
        lignes.append(setup.notes.replace("\n", " · "))
    for titre, colonnes, contenu in setup.groupes():
        lignes.append("")
        lignes.append(titre.upper()
                      + (f"   ({' / '.join(colonnes)})" if colonnes else ""))
        for ligne in contenu:
            lignes.append(f"  {ligne.libelle:<34}{'  '.join(ligne.valeurs)}")
    return os.linesep.join(lignes)
