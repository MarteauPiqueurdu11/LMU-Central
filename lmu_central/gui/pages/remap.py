"""Page Macros Volant.

Heberge l'interface de remap des molettes crantees, reprise du projet autonome.
Elle est construite a la premiere ouverture seulement : pygame met un instant a
s'initialiser, inutile de ralentir le demarrage du hub pour une page qu'on
n'ouvre pas forcement.
"""

import customtkinter as ctk

from .. import responsive, theme
from .base import Page


class RemapPage(Page):
    name = "remap"
    title = "Macros Volant"
    subtitle = ("Molettes crantées : choisir une position sans déclencher "
                "les actions traversées")
    order = 20

    def build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.entete = self.header(self, self.title, self.subtitle)
        self.entete.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        # Panneau dense : une fenetre courte doit pouvoir atteindre les cartes
        # du bas, d'ou le defilement vertical.
        self.zone = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.zone.grid(row=1, column=0, sticky="nsew")
        self.zone.grid_columnconfigure(0, weight=1)
        responsive.ascenseur_discret(self.zone, theme.BG)

        self.avertissement = None
        self.panneau = None

    def on_show(self):
        if self.panneau is not None:
            return
        self.app.set_status("Initialisation du volant…")
        self.after(50, self._construire_panneau)

    def _construire_panneau(self):
        try:
            from ...remap.panneau import PanneauRemap
            self.panneau = PanneauRemap(self.zone)
        except Exception as exc:  # pygame ou volant indisponible
            self._avertir(f"Impossible de charger le module de remap : {exc}")
            self.app.set_status("Macros indisponibles", error=True)
            return

        self.panneau.grid(row=1, column=0, sticky="nsew")
        self.zone.grid_rowconfigure(1, weight=1)
        self._annoncer_origine()

    def _annoncer_origine(self):
        """Dit d'ou viennent les reglages quand ce n'est pas l'endroit habituel.

        Des molettes vides, sans un mot, se lisent comme une perte de donnees ;
        c'est en general que l'application tourne sous un autre profil Windows
        et n'a pas trouve la configuration. Le silence est ici le vrai defaut.
        """
        from ...remap import config

        origine = config.ancienne_origine
        if origine is None:
            self.app.set_status("Macros prêtes")
        elif origine:
            self.app.set_status(f"Macros prêtes — réglages repris de {origine}")
        else:
            self._avertir(
                "Aucune configuration trouvée : les molettes repartent des "
                f"valeurs d'usine.\nElles seront enregistrées dans {config.DOSSIER}.")
            self.app.set_status("Macros prêtes — configuration neuve", error=True)

    def _avertir(self, message):
        if self.avertissement is None:
            self.avertissement = ctk.CTkLabel(
                self.zone, text="", font=self.f["small"], text_color=theme.TEXT_DIM,
                anchor="w", justify="left", fg_color=theme.SURFACE, corner_radius=8)
            self.avertissement.grid(row=0, column=0, sticky="ew", pady=(0, 10),
                                    ipadx=14, ipady=10)
        self.avertissement.configure(text=message)

    def on_close(self):
        if self.panneau is not None:
            self.panneau.fermer()
