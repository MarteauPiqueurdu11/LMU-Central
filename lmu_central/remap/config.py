"""
Chargement et sauvegarde de la configuration, dans config.json.

Le fichier est cree avec des valeurs par defaut au premier lancement. Toute
cle absente est completee par sa valeur par defaut, ce qui permet d'ajouter
des reglages plus tard sans casser un fichier existant.

Une configuration au format mono-molette (anterieure) est convertie
automatiquement au format multi-molettes.
"""

import copy
import json
import os
import sys

# La configuration vit avec celle du hub : dossier .cache du projet en
# developpement, profil utilisateur une fois empaquete en .exe.
from ..core.cache import CACHE_DIR

DOSSIER = str(CACHE_DIR)
FICHIER_CONFIG = os.path.join(DOSSIER, "remap-molettes.json")

NOM_SECOURS = "remap-config-origine.json"
DOSSIER_SECOURS = "sauvegardes"

# Ou l'application est reprise en cas de configuration manquante. Sans ce
# filet, elle repart des valeurs d'usine — et les molettes se retrouvent muettes
# alors que les reglages existent, quelque part, sur la machine.
ancienne_origine = None  # rempli par `charger` quand le filet a servi


def _destinations_de_secours():
    """Ou l'on **entretient** une copie de la configuration.

    Uniquement a cote de l'executable : c'est le seul endroit qui ne depende
    pas du compte Windows qui lance le programme. En developpement la liste est
    vide — le dossier `sauvegardes/` du projet est une archive, pas un cache,
    et rien n'a a le reecrire.
    """
    if not getattr(sys, "_MEIPASS", None):
        return []
    dossier = os.path.dirname(os.path.abspath(sys.executable))
    return [os.path.join(dossier, DOSSIER_SECOURS, NOM_SECOURS)]


def _entretenir_le_secours(config):
    """Tient la copie a jour, pour qu'elle vaille autre chose qu'un souvenir.

    Une copie figee le jour de la compilation ne sauve qu'une fois : au
    prochain incident elle rendrait des raccourcis perimes. On la reecrit donc
    a chaque enregistrement — jamais avec les valeurs d'usine, qui
    effaceraient une copie valable.
    """
    if _est_vierge(config):
        return
    texte = json.dumps(config, indent=2, ensure_ascii=False)
    for chemin in _destinations_de_secours():
        try:
            if os.path.exists(chemin):
                with open(chemin, encoding="utf-8") as fichier:
                    if fichier.read() == texte:
                        continue
            os.makedirs(os.path.dirname(chemin), exist_ok=True)
            with open(chemin, "w", encoding="utf-8") as fichier:
                fichier.write(texte)
        except OSError:
            continue  # dossier en lecture seule (Program Files) : tant pis


def _emplacements_de_secours():
    """Tous les endroits ou une configuration connue peut se trouver.

    Du plus frais au plus ancien. Toutes appartiennent a l'utilisateur
    courant : **aucune ne vient de l'interieur du programme**. Une copie
    embarquee a la compilation serait celle de qui a compile, et elle
    s'installerait toute seule au premier lancement chez n'importe qui
    d'autre — macros etrangeres, numeros de boutons d'un autre volant. Le
    filet doit rattraper une configuration perdue, jamais en inventer une.

    Reste donc le dossier de l'executable : le seul endroit qui appartienne a
    l'utilisateur et qui reste accessible quand l'application tourne sous un
    autre profil Windows, par exemple apres une elevation en administrateur.
    Cette copie-la, c'est l'application elle-meme qui l'ecrit, sur la machine
    de celui qui s'en sert — elle ne peut donc contenir que ses reglages.

    En developpement la liste est vide : la configuration vit dans `.cache/`,
    et il n'y a pas de second profil Windows dont il faudrait se proteger.
    """
    chemins = []

    if getattr(sys, "_MEIPASS", None):
        pres_de_l_exe = os.path.dirname(os.path.abspath(sys.executable))
        for dossier in (pres_de_l_exe, os.path.dirname(pres_de_l_exe)):
            chemins.append(os.path.join(dossier, DOSSIER_SECOURS, NOM_SECOURS))
            chemins.append(os.path.join(dossier, NOM_SECOURS))
    return chemins


def _recuperer_ancienne_config():
    """Renvoie le contenu d'une configuration de secours, ou None."""
    for chemin in _emplacements_de_secours():
        if os.path.exists(chemin):
            try:
                with open(chemin, encoding="utf-8") as fichier:
                    return json.load(fichier), chemin
            except (OSError, ValueError):
                continue
    return None

NB_POSITIONS = 12

# Champs conserves pour chaque action. Les versions precedentes stockaient
# aussi un type ("gamepad" ou "clavier") et un bouton de manette virtuelle :
# ces cles sont retirees au chargement, l'application n'envoyant plus que des
# combinaisons clavier.
CLES_ACTION = ("touches", "libelle")


def actions_par_defaut(nb_positions=NB_POSITIONS):
    actions = {}
    for position in range(1, nb_positions + 1):
        actions[str(position)] = {
            "touches": "",
            "libelle": f"Position {position}",
        }
    return actions


# Boutons du volant a renseigner pour qu'une molette soit active.
CLES_BOUTONS = ("increment", "decrement", "confirm")


def molette_par_defaut(nom, increment=None, decrement=None, confirm=None):
    return {
        "nom": nom,
        "boutons": {
            "increment": increment,
            "decrement": decrement,
            "confirm": confirm,
        },
        "nb_positions": NB_POSITIONS,
        "position_depart": 1,
        "position_reset": 1,
        "actions": actions_par_defaut(),
    }


DEFAUTS = {
    "molettes": [
        molette_par_defaut("Molette 1", increment=48, decrement=49, confirm=1),
        molette_par_defaut("Molette 2"),
    ],
    # Duree de maintien d'une frappe clavier. Un appui instantane est souvent
    # rate par les interfaces qui capturent un raccourci (Voicemod, OBS...).
    "duree_touche": 0.06,
    # Secondes avant l'envoi declenche par le bouton "Envoyer", le temps de
    # basculer sur la fenetre de l'appli qui attend une touche.
    "delai_test": 4,
    "overlay": {
        "affiche": True,
        # True : une seule ligne par molette (position courante uniquement).
        # False : la liste complete des positions.
        "compact": True,
        "clic_traversant": False,
        "opacite": 0.85,
        "taille_police": 11,
        "x": 40,
        "y": 40,
    },
}


def _fusionner(defauts, charge):
    """Complete recursivement `charge` avec les cles manquantes de `defauts`."""
    resultat = copy.deepcopy(defauts)
    for cle, valeur in charge.items():
        if cle in resultat and isinstance(resultat[cle], dict) and isinstance(valeur, dict):
            resultat[cle] = _fusionner(resultat[cle], valeur)
        else:
            resultat[cle] = valeur
    return resultat


def _migrer(charge):
    """Convertit une config mono-molette au format multi-molettes."""
    if "molettes" in charge or "boutons_volant" not in charge:
        return charge

    migree = copy.deepcopy(charge)

    premiere = molette_par_defaut("Molette 1")
    premiere["boutons"] = migree.pop("boutons_volant")
    premiere["actions"] = migree.pop("actions", premiere["actions"])
    premiere["nb_positions"] = migree.pop("nb_positions", NB_POSITIONS)
    premiere["position_depart"] = migree.pop("position_depart", 1)
    premiere["position_reset"] = migree.pop("position_reset", 1)

    migree["molettes"] = [premiere, molette_par_defaut("Molette 2")]
    return migree


def _completer_molettes(config):
    """Applique les defauts a chaque molette, quel que soit leur nombre."""
    modele = molette_par_defaut("")
    molettes = []
    for brute in config.get("molettes", []):
        molette = _fusionner(modele, brute)
        # "reset" a existe comme bouton du volant ; il est remplace par le
        # bouton "Position -> 1" de l'interface.
        molette["boutons"] = {c: molette["boutons"].get(c) for c in CLES_BOUTONS}
        # "type" et "bouton" datent de la manette virtuelle, desormais retiree.
        molette["actions"] = {
            position: {cle: action.get(cle, "") for cle in CLES_ACTION}
            for position, action in molette["actions"].items()
        }
        molettes.append(molette)
    config["molettes"] = molettes
    return config


def charger():
    """Renvoie la configuration, en creant le fichier au besoin.

    Au premier lancement sur une machine, il n'y a rien a reprendre : les
    molettes partent vides et c'est le bouton « Detecter » qui apprend les
    boutons de ce volant-la. Le filet de secours ne sert qu'a retrouver une
    configuration **deja ecrite par cet utilisateur** et devenue invisible,
    typiquement apres une elevation en administrateur.
    """
    global ancienne_origine
    ancienne_origine = None

    if not os.path.exists(FICHIER_CONFIG):
        ancienne = _recuperer_ancienne_config()
        if ancienne:
            charge, origine = ancienne
            config = _completer_molettes(_fusionner(DEFAUTS, _migrer(charge)))
            sauver(config)
            ancienne_origine = origine
            print(f"remap : configuration reprise de {origine}")
            return config
        # Plus rien nulle part : on repart de zero, mais l'interface doit le
        # dire. Des molettes vides sans explication passent pour une panne.
        ancienne_origine = ""
        sauver(DEFAUTS)
        return copy.deepcopy(DEFAUTS)

    try:
        with open(FICHIER_CONFIG, encoding="utf-8") as fichier:
            charge = json.load(fichier)
    except (OSError, ValueError):
        # Fichier illisible ou corrompu : on repart des defauts sans ecraser.
        return copy.deepcopy(DEFAUTS)

    config = _completer_molettes(_fusionner(DEFAUTS, _migrer(charge)))

    # Un fichier qui ne contient que les valeurs d'usine n'apprend rien : il a
    # ete ecrit par une session qui n'avait, elle non plus, rien trouve. Si une
    # copie de secours existe, elle vaut mieux. On ne fait ce remplacement que
    # dans ce cas precis, pour ne jamais ressusciter des reglages effaces
    # volontairement.
    if _est_vierge(config):
        ancienne = _recuperer_ancienne_config()
        if ancienne:
            reprise = _completer_molettes(_fusionner(DEFAUTS, _migrer(ancienne[0])))
            if not _est_vierge(reprise):
                sauver(reprise)
                ancienne_origine = ancienne[1]
                print(f"remap : configuration d'usine remplacee par {ancienne[1]}")
                return reprise

    # Tout va bien : c'est le moment d'entretenir la copie de secours. Attendre
    # une modification reviendrait a n'avoir aucun filet tant que l'utilisateur
    # ne touche a rien — soit exactement quand il n'a rien a se reprocher.
    _entretenir_le_secours(config)
    return config


def _est_vierge(config):
    """Vrai si la configuration est exactement celle sortie d'usine."""
    neuve = _completer_molettes(copy.deepcopy(DEFAUTS))
    return config.get("molettes") == neuve["molettes"]


def sauver(config):
    """Ecrit la configuration sur disque. Renvoie True si l'ecriture a reussi."""
    try:
        os.makedirs(DOSSIER, exist_ok=True)
        with open(FICHIER_CONFIG, "w", encoding="utf-8") as fichier:
            json.dump(config, fichier, indent=2, ensure_ascii=False)
    except OSError:
        return False
    _entretenir_le_secours(config)
    return True
