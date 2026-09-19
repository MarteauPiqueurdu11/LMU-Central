"""Composants reutilisables du hub."""

import customtkinter as ctk

from . import responsive, theme

RANK_ORDER = ["Bronze", "Silver", "Gold", "Platinum"]

# Largeur moyenne d'un caractere en Segoe UI 12, mesuree a l'oeil sur les
# libelles du jeu. Sert a couper un texte avant qu'il n'elargisse sa colonne.
LARGEUR_CARACTERE = 6.5


def tronquer(texte, largeur):
    """Coupe au nombre de caracteres que la colonne peut montrer.

    Un CTkLabel ne rogne pas son texte : il pousse la colonne, qui pousse ses
    voisines hors de la fenetre. Mieux vaut couper nous-memes.
    """
    limite = max(6, int((largeur - 6) / LARGEUR_CARACTERE))
    return texte if len(texte) <= limite else texte[:limite - 1] + "…"


def next_rank(rank, tier):
    """Rang suivant sous forme 'Gold 1', ou None si deja au sommet."""
    if tier < 3:
        return f"{rank} {tier + 1}"
    idx = RANK_ORDER.index(rank) if rank in RANK_ORDER else -1
    if idx < 0 or idx == len(RANK_ORDER) - 1:
        return None
    return f"{RANK_ORDER[idx + 1]} 1"


class Card(ctk.CTkFrame):
    """Panneau de base, fond surface et bordure discrete."""

    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", theme.SURFACE)
        kwargs.setdefault("corner_radius", 10)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", theme.BORDER)
        super().__init__(master, **kwargs)


class RatingCard(Card):
    """Carte d'un rating : rang, barre de progression, valeur brute.

    `exact=False` signale une valeur tronquee par le serveur (autres joueurs).
    """

    def __init__(self, master, f, label):
        super().__init__(master)
        self.f = f
        self.grid_columnconfigure(0, weight=1)

        self.label = ctk.CTkLabel(self, text=label, font=f["heading"],
                                  text_color=theme.TEXT_FAINT, anchor="w")
        self.label.grid(row=0, column=0, sticky="ew", padx=20, pady=(12, 2))

        self.rank_label = ctk.CTkLabel(self, text="—", font=f["display"],
                                       text_color=theme.TEXT, anchor="w")
        self.rank_label.grid(row=1, column=0, sticky="ew", padx=20)

        self.bar = ctk.CTkProgressBar(self, height=10, corner_radius=5,
                                      fg_color=theme.SURFACE_HI)
        self.bar.set(0)
        self.bar.grid(row=2, column=0, sticky="ew", padx=20, pady=(8, 5))

        self.pct_label = ctk.CTkLabel(self, text="—", font=f["title"],
                                      text_color=theme.TEXT, anchor="w")
        self.pct_label.grid(row=3, column=0, sticky="ew", padx=20)

        self.detail = ctk.CTkLabel(self, text="", font=f["small"],
                                   text_color=theme.TEXT_DIM, anchor="w",
                                   justify="left")
        self.detail.grid(row=4, column=0, sticky="ew", padx=20, pady=(2, 12))

        # Sans wraplength, une ligne trop longue elargit la carte et pousse sa
        # voisine hors de la fenetre au lieu de passer a la ligne.
        responsive.suivre_largeur(
            self, lambda largeur: self.detail.configure(wraplength=max(120, largeur - 40)))

    def update_rating(self, rank, tier, progress, raw_label, raw_value,
                      exact=True, extra=""):
        color = theme.rank_color(rank)
        self.rank_label.configure(text=f"{rank} {tier}", text_color=color)
        self.bar.configure(progress_color=color)
        self.bar.set(max(0.0, min(1.0, progress / 100)))
        self.pct_label.configure(
            text=f"{progress:.2f} %" if exact else f"~{progress:.0f} %",
            text_color=theme.TEXT if exact else theme.TEXT_DIM)

        if exact:
            lines = [f"{raw_label} {raw_value:.2f}"]
            nxt = next_rank(rank, tier)
            if nxt:
                lines.append(f"Encore {100 - progress:.2f} % pour {nxt}")
        else:
            lines = [f"{raw_label} masqué par le serveur"]
        if extra:
            lines.append(extra)
        self.detail.configure(text="\n".join(lines))


class FriendRow(ctk.CTkFrame):
    """Une ligne d'ami : nom, DR, SR, nombre de courses."""

    def __init__(self, master, f, friend, races, colonnes=4):
        """`colonnes` limite l'affichage quand la fenetre est etroite.

        On coupe par la fin : le nom et le DR passent avant le SR, qui passe
        avant le nombre de courses.
        """
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1, minsize=150)
        for colonne, largeur in ((1, 130), (2, 130), (3, 80)):
            self.grid_columnconfigure(colonne, minsize=largeur if colonne < colonnes else 0)
        derniere = colonnes - 1

        dr = friend.get("driverRank") or {}
        sr = friend.get("safetyRank") or {}
        name = friend.get("name") or friend.get("username") or "?"

        ctk.CTkLabel(self, text=name, font=f["body"], text_color=theme.TEXT,
                     anchor="w").grid(row=0, column=0, sticky="ew",
                                      padx=(16, 8) if derniere else (16, 16), pady=7)

        for col, data in ((1, dr), (2, sr)):
            if col >= colonnes:
                continue
            text = f"{data.get('rank', '?')} {data.get('tier', '?')}  ~{data.get('progress', 0):.0f} %"
            ctk.CTkLabel(self, text=text, font=f["small"],
                         text_color=theme.rank_color(data.get("rank")),
                         anchor="w").grid(row=0, column=col, sticky="ew",
                                          padx=(8, 16) if col == derniere else 8)

        if colonnes > 3:
            ctk.CTkLabel(self, text=f"{races} courses" if races else "—",
                         font=f["tiny"], text_color=theme.TEXT_FAINT,
                         anchor="e").grid(row=0, column=3, sticky="ew", padx=(8, 16))
