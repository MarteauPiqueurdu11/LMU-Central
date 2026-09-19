"""Rendu terminal partage par tous les modules du hub."""

import io
import os
import sys

from ..core import timefmt

RANK_ORDER = ["Bronze", "Silver", "Gold", "Platinum"]

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[38;5;203m"
GREEN = "\033[38;5;114m"
BLUE = "\033[38;5;75m"

RANK_COLOR = {
    "Bronze": "\033[38;5;173m",
    "Silver": "\033[38;5;252m",
    "Gold": "\033[38;5;220m",
    "Platinum": "\033[38;5;87m",
}

_enabled = True


def setup(color=True):
    """Force UTF-8 sur la sortie et active les sequences ANSI sous Windows."""
    global _enabled
    _enabled = color
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if os.name == "nt" and color:
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


def c(text, code):
    """Colore un texte, sauf si les couleurs sont desactivees."""
    return f"{code}{text}{RESET}" if _enabled else str(text)


def rank_color(rank):
    return RANK_COLOR.get(rank, "") if _enabled else ""


def title(text):
    print()
    print(f"  {c(text, BOLD)}")


def section(text):
    print()
    print(f"  {c(text, DIM)}")


def note(text):
    print(f"  {c(text, DIM)}")


def error(text):
    print(f"\n  {c('Erreur', RED)} : {text}\n", file=sys.stderr)


def bar(pct, width=28, color=""):
    pct = max(0.0, min(100.0, float(pct)))
    filled = int(round(pct / 100 * width))
    if not _enabled:
        return "#" * filled + "-" * (width - filled)
    return f"{color}{'█' * filled}{RESET}{DIM}{'░' * (width - filled)}{RESET}"


def next_rank(rank, tier):
    """Rang suivant sous forme 'Gold 1', ou None si deja au sommet."""
    if tier < 3:
        return f"{rank} {tier + 1}"
    idx = RANK_ORDER.index(rank) if rank in RANK_ORDER else -1
    if idx < 0 or idx == len(RANK_ORDER) - 1:
        return None
    return f"{RANK_ORDER[idx + 1]} 1"


def rating_block(label, rank, tier, progress, raw_label, raw_value, exact=True):
    """Affiche un rating complet : rang, barre, pourcentage, valeur brute."""
    col = rank_color(rank)
    pct = f"{progress:.2f} %" if exact else f"~{progress:.0f} %"
    section(label)
    print(f"  {c(f'{rank} {tier}', BOLD + col)}   {bar(progress, color=col)}  {c(pct, BOLD)}")
    detail = f"{raw_label} {raw_value:.2f}" if exact else f"{raw_label} masque par le serveur"
    nxt = next_rank(rank, tier)
    if nxt and exact:
        detail += f"   ·   encore {100 - progress:.2f} % pour {nxt}"
    note(detail)


local_time = timefmt.local_time
