"""Palette et typographie du hub."""

import sys
from pathlib import Path

import customtkinter as ctk

# --- couleurs ---
BG = "#0D1117"          # fond de la fenetre
SURFACE = "#161B22"     # cartes
SURFACE_HI = "#1C2129"  # survol / elements actifs
BORDER = "#272E38"
TEXT = "#E6EDF3"
TEXT_DIM = "#8B949E"
TEXT_FAINT = "#5B6570"
ACCENT = "#FF1D43"      # rouge officiel Le Mans Ultimate (releve sur le logo du jeu)
ACCENT_HI = "#FF4D6A"   # meme teinte, desaturee : survol
OK = "#3FB950"
WARN = "#D29922"

RANK_COLORS = {
    "Bronze": "#C87B4A",
    "Silver": "#C9D1D9",
    "Gold": "#E3B341",
    "Platinum": "#5BC8E0",
}

FALLBACK_RANK = "#8B949E"

FAMILY = "Segoe UI"

# Polices a chasse fixe, de la plus lisible a la plus repandue. Cascadia Mono
# distingue nettement l et 1, O et 0 : c'est ce qui compte pour relire un
# raccourci clavier d'un coup d'oeil.
MONO_CANDIDATES = ("Cascadia Mono", "Cascadia Code", "Consolas", "Lucida Console")
_mono = None


def mono_family():
    """Meilleure police a chasse fixe installee. Necessite une fenetre Tk."""
    global _mono
    if _mono is None:
        try:
            from tkinter import font as tkfont

            disponibles = set(tkfont.families())
        except Exception:
            disponibles = set()
        _mono = next((f for f in MONO_CANDIDATES if f in disponibles),
                     MONO_CANDIDATES[-1])
    return _mono


def _dossier_assets():
    """Ou vivent icone et logo.

    En .exe, PyInstaller extrait les donnees embarquees dans un dossier
    temporaire que `sys._MEIPASS` designe.
    """
    base = getattr(sys, "_MEIPASS", None)
    racine = Path(base) if base else Path(__file__).resolve().parents[2]
    return racine / "assets"


def chemin_icone():
    """L'icone .ico, pour la fenetre et la barre des taches. None si absente."""
    chemin = _dossier_assets() / "icon.ico"
    return chemin if chemin.exists() else None


def charger_logo(taille):
    """Le logo en CTkImage, pour l'afficher dans l'interface.

    Necessite une fenetre Tk existante. Rend None si le fichier manque : le
    hub doit rester utilisable sans son logo.
    """
    chemin = _dossier_assets() / "logo.png"
    if not chemin.exists():
        return None
    try:
        from PIL import Image

        return ctk.CTkImage(Image.open(chemin), size=(taille, taille))
    except Exception:
        return None


def rank_color(rank):
    return RANK_COLORS.get(rank, FALLBACK_RANK)


def apply():
    """Applique le mode sombre. A appeler avant de creer la fenetre."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")


# --- polices (a instancier apres la creation de la fenetre Tk) ---

def fonts():
    return {
        "display": ctk.CTkFont(family=FAMILY, size=29, weight="bold"),
        "title": ctk.CTkFont(family=FAMILY, size=19, weight="bold"),
        "heading": ctk.CTkFont(family=FAMILY, size=13, weight="bold"),
        "body": ctk.CTkFont(family=FAMILY, size=13),
        "small": ctk.CTkFont(family=FAMILY, size=12),
        "tiny": ctk.CTkFont(family=FAMILY, size=11),
        "mono": ctk.CTkFont(family=mono_family(), size=12),
    }
