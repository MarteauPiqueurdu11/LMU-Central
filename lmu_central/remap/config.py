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

# La configuration vit avec celle du hub : dossier .cache du projet en
# developpement, dossier `donnees` a cote de l'executable une fois empaquete.
from ..core.cache import CACHE_DIR

DOSSIER = str(CACHE_DIR)
FICHIER_CONFIG = os.path.join(DOSSIER, "remap-molettes.json")

# Vrai quand `charger` n'a trouve aucune configuration : c'est un premier
# lancement, pas une perte. L'interface s'en sert pour le dire autrement.
premier_lancement = False


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

    Au premier lancement, les molettes partent vides et c'est le bouton
    « Detecter » qui apprend les boutons de ce volant-la. Rien n'est repris
    d'ailleurs : la configuration vit dans le dossier de l'application, donc
    elle le suit quand on le deplace, et elle ne depend plus du compte Windows
    qui lance le programme — ce contre quoi il fallait autrefois un filet.
    """
    global premier_lancement
    premier_lancement = False

    if not os.path.exists(FICHIER_CONFIG):
        # Des molettes vides sans un mot se lisent comme une panne : on marque
        # le premier lancement pour que l'interface explique quoi faire.
        premier_lancement = True
        sauver(DEFAUTS)
        return copy.deepcopy(DEFAUTS)

    try:
        with open(FICHIER_CONFIG, encoding="utf-8") as fichier:
            charge = json.load(fichier)
    except (OSError, ValueError):
        # Fichier illisible ou corrompu : on repart des defauts sans ecraser.
        return copy.deepcopy(DEFAUTS)

    return _completer_molettes(_fusionner(DEFAUTS, _migrer(charge)))


def sauver(config):
    """Ecrit la configuration sur disque. Renvoie True si l'ecriture a reussi."""
    try:
        os.makedirs(DOSSIER, exist_ok=True)
        with open(FICHIER_CONFIG, "w", encoding="utf-8") as fichier:
            json.dump(config, fichier, indent=2, ensure_ascii=False)
    except OSError:
        return False
    return True
