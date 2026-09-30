"""Construit LMU Central.exe avec PyInstaller.

    py -3 build.py

Le resultat atterrit dans dist/LMU Central.exe — un fichier unique, autonome,
qui ne demande ni Python ni dependance sur la machine cible.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
NAME = "LMU Central"
ICON = ROOT / "assets" / "icon.ico"


def main():
    if not ICON.exists():
        print("Generation de l'icone...")
        subprocess.run([sys.executable, str(ROOT / "make_icon.py")], check=True)

    for folder in ("build", "dist"):
        shutil.rmtree(ROOT / folder, ignore_errors=True)

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
        "--noconfirm", "--clean",
        str(ROOT / "app.py"),
    ]
    print(" ".join(cmd), "\n")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        return result.returncode

    exe = ROOT / "dist" / f"{NAME}.exe"
    if exe.exists():
        print(f"\nOK : {exe}  ({exe.stat().st_size / 1_048_576:.1f} Mo)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
