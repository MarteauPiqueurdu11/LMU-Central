"""LMU Central — interface graphique.

    py -3 app.py

Le hub demarre normalement, sans elevation. Seules les applications **elevees**
(Le Mans Ultimate, lance par EasyAntiCheat) exigent que le hub le soit aussi
pour recevoir les raccourcis du module Macros Volant ; Voicemod, Discord ou OBS
fonctionnent sans.

Au besoin : clic droit sur l'executable > Executer en tant qu'administrateur.
"""

import ctypes
import sys

from lmu_central.gui.app import run

# Identifiant applicatif Windows. Sans lui, la barre des taches rattache la
# fenetre a l'hote Python et affiche SON icone au lieu de celle du hub.
ID_APPLICATION = "LMU.Central"


def declarer_identite_windows():
    """Detache le hub de l'hote Python aux yeux de la barre des taches."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(ID_APPLICATION)
    except (AttributeError, OSError):
        pass


def main():
    declarer_identite_windows()
    return run() or 0


if __name__ == "__main__":
    sys.exit(main())
