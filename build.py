"""Construit LMU Central.exe, puis l archive a distribuer.

    py -3 build.py

Deux produits, a la racine du projet :

- `LMU Central.exe` — un fichier unique, autonome, qui ne demande ni Python
  ni dependance sur la machine cible. A la racine et non dans `dist/`, parce
  que l application est portable : elle ecrit ses donnees a cote d elle, donc
  l executable doit etre la ou l on veut que le dossier vive.
- `LMU-Central-vX.Y.Z.zip` — le dossier pret a partager : l executable et un
  LISEZ-MOI. On le pose ou l on veut, on double-clique, les donnees se
  rangent a cote.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
NAME = "LMU Central"
ICON = ROOT / "assets" / "icon.ico"

sys.path.insert(0, str(ROOT))
from lmu_central import __version__  # noqa: E402  (apres sys.path)

LISEZ_MOI = """LMU CENTRAL
===========

Pose ce dossier ou tu veux — Documents, Bureau, une cle USB — puis
double-clic sur « LMU Central.exe ».

Rien a installer.


AU PREMIER LANCEMENT
--------------------

Windows va rouspeter : l'executable n'est pas signe.
Clique sur « Informations complementaires », puis « Executer quand meme ».


TES DONNEES RESTENT DANS CE DOSSIER
-----------------------------------

L'application cree un sous-dossier « donnees » a cote d'elle. Tes reglages
de molettes, ton historique de ratings et les caches y vivent.

Consequences :
  - deplace le dossier ou tu veux, tout te suit ;
  - sauvegarder ce dossier, c'est tout sauvegarder ;
  - ne le mets pas dans « Program Files » : Windows y interdit l'ecriture.


LES QUATRE ONGLETS
------------------

Ratings    Ton DR et ton SR au centieme de pourcent, la ou le jeu arrondit
           a la dizaine. Les ratings de tes amis Steam, et l'historique de
           tes courses avec le gain ou la perte exacte de chacune.

Calendrier Les epreuves a venir, les amis deja inscrits, et le compte a
           rebours avant chaque depart.

Setups     Tes setups ranges par circuit, avec la valeur de chaque reglage
           et la comparaison de deux setups cote a cote.

Macros     Transforme les molettes crantees de ton volant en raccourcis
Volant     clavier. Au depart elles sont vides : clique sur « Detecter »,
           puis actionne le bouton voulu sur ton volant pour le lui
           apprendre.


FAUT-IL QUE LE JEU SOIT OUVERT ?
--------------------------------

Setups                : jamais, ce sont des fichiers sur ton disque.
Ratings et Calendrier : le jeu doit etre lance une fois, pour
                        s'authentifier. Tu as ensuite 30 minutes ou tout
                        marche, jeu ferme.

Passe ce delai, le hub affiche les dernieres valeurs connues avec leur
date. Relance Le Mans Ultimate pour rafraichir.


POUR AVOIR LE POURCENTAGE EXACT DE TES COURSES
----------------------------------------------

Laisse le hub ouvert pendant que tu joues, et laisse le jeu tourner une
minute de plus apres ta derniere course.

Le pourcentage gagne ou perdu n'existe nulle part sur les serveurs du jeu :
le hub le reconstruit en relevant ta valeur avant et apres chaque course, et
seul le jeu en cours d'execution peut la lui donner. Tes courses d'avant
l'installation n'auront donc que les chevrons du jeu.


LES MACROS VERS LE JEU DEMANDENT L'ADMINISTRATEUR
-------------------------------------------------

Le Mans Ultimate tourne en mode protege : pour lui envoyer des touches, le
hub doit etre lance en administrateur (clic droit, « Executer en tant
qu'administrateur »). Pour Discord, OBS ou Voicemod, c'est inutile.


TOUT EST EN LECTURE SEULE
-------------------------

Le hub ne modifie jamais ton profil, tes resultats ni tes fichiers de jeu.


Code source et mises a jour :
https://github.com/MarteauPiqueurdu11/LMU-Central
"""


def main():
    if not ICON.exists():
        print("Generation de l'icone...")
        subprocess.run([sys.executable, str(ROOT / "make_icon.py")], check=True)

    shutil.rmtree(ROOT / "build", ignore_errors=True)
    shutil.rmtree(ROOT / "dist", ignore_errors=True)  # produit des versions < 1.0.2

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", NAME,
        "--onefile",            # un seul executable a distribuer
        "--windowed",           # pas de console derriere la fenetre
        "--icon", str(ICON),          # icone du fichier .exe
        # Le dossier entier : la fenetre et la barre des taches lisent
        # l'icone que Tk porte, pas celle du binaire, et la barre laterale
        # affiche le logo en PNG.
        "--add-data", f"{ROOT / 'assets'}{os.pathsep}assets",
        # Rien de plus n'est embarque ici. La configuration des molettes, en
        # particulier, ne doit PAS l'etre : elle contient les macros et les
        # numeros de boutons de qui a compile. Embarquee, elle s'installait
        # toute seule au premier lancement sur la machine de n'importe qui
        # d'autre — des raccourcis etrangers, sur un volant qui n'a pas les
        # memes boutons. Le filet de securite passe par la copie tenue a jour
        # a cote de l'executable (voir remap/config.py).
        "--collect-all", "customtkinter",  # embarque ses themes JSON
        # Indispensable : les modules et pages sont decouverts dynamiquement par
        # pkgutil. Sans cette option, PyInstaller ne les embarque pas (aucun
        # import statique ne les mentionne) et l'application demarre vide.
        "--collect-submodules", "lmu_central",
        # Le module Macros Volant lit le volant (pygame) et injecte des frappes
        # (keyboard) ; PIL sert aux widgets dessines a la main.
        "--hidden-import", "keyboard",
        "--hidden-import", "pygame",
        "--hidden-import", "PIL",
        # L executable atterrit a la racine : c est lui qui fixe ou vivent
        # les donnees, donc sa place n est pas un sous-dossier de build.
        "--distpath", str(ROOT),
        "--noconfirm", "--clean",
        str(ROOT / "app.py"),
    ]
    print(" ".join(cmd), "\n")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        return result.returncode

    exe = ROOT / f"{NAME}.exe"
    if not exe.exists():
        print("\nPyInstaller n a pas produit d executable.")
        return 1

    print(f"\nOK : {exe}  ({exe.stat().st_size / 1_048_576:.1f} Mo)")
    archive = archiver(exe)
    print(f"OK : {archive}  ({archive.stat().st_size / 1_048_576:.1f} Mo)")
    return 0


def archiver(exe):
    """Met l executable et son LISEZ-MOI dans un zip, sous un dossier a son nom.

    Le zip contient un dossier et non des fichiers en vrac : decompresse, on
    obtient « LMU Central/ » prete a etre posee ou l on veut, et non deux
    fichiers laches au milieu du dossier Telechargements.
    """
    mise_en_forme = ROOT / "build" / "archive" / NAME
    shutil.rmtree(mise_en_forme.parent, ignore_errors=True)
    mise_en_forme.mkdir(parents=True)

    shutil.copy2(exe, mise_en_forme / exe.name)
    (mise_en_forme / "LISEZ-MOI.txt").write_text(LISEZ_MOI, encoding="utf-8")

    base = ROOT / f"{NAME.replace(' ', '-')}-v{__version__}"
    chemin = shutil.make_archive(str(base), "zip",
                                 root_dir=str(mise_en_forme.parent),
                                 base_dir=NAME)
    return Path(chemin)


if __name__ == "__main__":
    sys.exit(main())
