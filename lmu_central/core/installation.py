"""Ou Le Mans Ultimate est installe.

Le hub n'en a pas eu besoin jusqu'ici : tout passait par le serveur local du
jeu ou par le backend. Les setups, eux, sont des fichiers poses sur le disque,
et il faut donc savoir ou.

Steam n'est pas obligatoirement sur C:. On lit sa configuration plutot que de
deviner : la cle de registre donne le dossier de Steam, `libraryfolders.vdf`
donne toutes les bibliotheques, et on cherche le jeu dans chacune.
"""

import os
import re
from pathlib import Path

from .errors import HubError

NOM_DOSSIER = "Le Mans Ultimate"

# Variable d'environnement de secours, si la detection automatique echoue ou
# si le jeu a ete copie ailleurs.
VARIABLE = "LMU_CENTRAL_JEU"

# `"path"  "D:\\SteamLibrary"` dans libraryfolders.vdf.
CHEMIN_VDF = re.compile(r'"path"\s+"([^"]+)"')

_trouve = None


def _depuis_registre():
    """Dossier d'installation de Steam, lu dans le registre Windows."""
    try:
        import winreg
    except ImportError:
        return None
    for ruche, cle in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                       (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
        for valeur in ("SteamPath", "InstallPath"):
            try:
                with winreg.OpenKey(ruche, cle) as poignee:
                    chemin = Path(winreg.QueryValueEx(poignee, valeur)[0])
            except OSError:
                continue
            if chemin.is_dir():
                return chemin
    return None


def _bibliotheques(steam):
    """Toutes les bibliotheques Steam declarees, celle de base comprise."""
    vus, dossiers = set(), []
    for candidat in [steam] + _lire_vdf(steam):
        try:
            resolu = candidat.resolve()
        except OSError:
            continue
        if resolu not in vus and resolu.is_dir():
            vus.add(resolu)
            dossiers.append(resolu)
    return dossiers


def _lire_vdf(steam):
    fichier = steam / "steamapps" / "libraryfolders.vdf"
    try:
        texte = fichier.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    # Les chemins y sont echappes a la mode C : "D:\\Jeux" designe D:\Jeux.
    return [Path(brut.replace("\\\\", "\\")) for brut in CHEMIN_VDF.findall(texte)]


def _candidats():
    steam = _depuis_registre()
    bases = _bibliotheques(steam) if steam else []
    for lettre in ("C", "D", "E", "F", "G"):
        bases.append(Path(f"{lettre}:/SteamLibrary"))
        bases.append(Path(f"{lettre}:/Program Files (x86)/Steam"))
    for base in bases:
        yield base / "steamapps" / "common" / NOM_DOSSIER


def trouver(force=False):
    """Dossier d'installation du jeu, ou None s'il reste introuvable."""
    global _trouve
    if _trouve is not None and not force:
        return _trouve

    impose = os.environ.get(VARIABLE)
    if impose:
        chemin = Path(impose)
        # Un chemin impose a la main merite un verdict franc : le signaler
        # plutot que de repartir en silence sur une detection automatique qui
        # trouverait une autre installation que celle voulue.
        if not (chemin / "UserData").is_dir():
            raise HubError(
                f"{VARIABLE} pointe sur {chemin}, ou il n'y a pas de dossier "
                "UserData.\n  Corrige la variable, ou supprime-la pour laisser "
                "le hub chercher tout seul.")
        _trouve = chemin
        return _trouve

    for candidat in _candidats():
        if (candidat / "UserData").is_dir():
            _trouve = candidat
            return _trouve
    return None


def exiger():
    """Comme `trouver`, mais leve une erreur explicite plutot que de rendre None."""
    chemin = trouver()
    if chemin is None:
        raise HubError(
            "Installation de Le Mans Ultimate introuvable.\n"
            f"  Indique-la avec la variable d'environnement {VARIABLE}.")
    return chemin


def dossier_setups():
    """Le dossier ou le jeu range les setups, un sous-dossier par circuit."""
    return exiger() / "UserData" / "player" / "Settings"
