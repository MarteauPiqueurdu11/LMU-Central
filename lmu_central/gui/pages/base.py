"""Socle des pages de l'interface.

Ajouter une page = deposer un fichier dans lmu_central/gui/pages/ definissant une
sous-classe de Page. Elle apparait automatiquement dans la barre laterale.
"""

import customtkinter as ctk

from .. import responsive, theme


class Page(ctk.CTkFrame):
    name = ""        # identifiant interne
    title = ""       # intitule dans la barre laterale
    subtitle = ""    # ligne d'explication en tete de page
    order = 100      # position dans la barre laterale
    available = True  # False = grisee (fonctionnalite a venir)

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.f = app.f
        self.ctx = app.ctx
        self.build()

    def build(self):
        """Construit l'interface de la page (appele une seule fois)."""

    def on_show(self):
        """Appele chaque fois que la page devient visible."""

    def on_close(self):
        """Appele a la fermeture de l'application : liberer les ressources."""

    # --- helpers ---

    def header(self, parent, title, subtitle=""):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(box, text=title, font=self.f["title"],
                     text_color=theme.TEXT, anchor="w").pack(anchor="w")
        if subtitle:
            ligne = ctk.CTkLabel(box, text=subtitle, font=self.f["small"],
                                 text_color=theme.TEXT_DIM, anchor="w",
                                 justify="left")
            ligne.pack(anchor="w", fill="x", pady=(2, 0))
            responsive.replier_texte(ligne, self, marge=130)
        return box
