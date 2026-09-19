"""Page Driver & Safety Rating.

Le bas de la page bascule entre deux vues : les amis Steam, ou l'historique
complet des courses avec ses filtres.
"""

from ...core import courses as courses_core
from ...core import ratings as ratings_core
from ...core.timefmt import local_time
from .. import responsive, theme
from ..vues import VueAmis, VueCourses
from ..widgets import Card, RatingCard
from .base import Page

import customtkinter as ctk

AMIS, COURSES = "Amis Steam", "Historique"

# En dessous de cette largeur, les deux cartes de rating ne tiennent plus cote
# a cote sans se marcher dessus : on les empile.
SEUIL_CARTES = 620


class RatingsPage(Page):
    name = "ratings"
    title = "Ratings"
    subtitle = "Ton DR et ton SR au centième de pourcent"
    order = 10

    def build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._construire_entete()

        # --- bandeau hors ligne ---
        self.banner = Card(self, fg_color="#2A1F16", border_color="#5A3E1E")
        self.banner_label = ctk.CTkLabel(self.banner, text="", font=self.f["small"],
                                         text_color=theme.WARN, anchor="w",
                                         justify="left")
        self.banner_label.pack(anchor="w", fill="x", padx=16, pady=10)
        responsive.replier_texte(self.banner_label, self, marge=48)

        # --- les deux ratings ---
        self.cartes = ctk.CTkFrame(self, fg_color="transparent")
        self.cartes.grid(row=2, column=0, sticky="ew")

        self.dr_card = RatingCard(self.cartes, self.f, "DRIVER RATING")
        self.sr_card = RatingCard(self.cartes, self.f, "SAFETY RATING")
        self._disposer_cartes(1)
        responsive.suivre_paliers(self, (SEUIL_CARTES,), self._disposer_cartes)

        self._construire_bas()
        self._loaded = False
        self._courses_chargees = False

    def _disposer_cartes(self, palier):
        """Les deux ratings cote a cote, ou l'un sous l'autre si c'est etroit."""
        if palier:
            self.cartes.grid_columnconfigure((0, 1), weight=1, uniform="r")
            self.dr_card.grid(row=0, column=0, columnspan=1, sticky="nsew",
                              padx=(0, 7), pady=0)
            self.sr_card.grid(row=0, column=1, columnspan=1, sticky="nsew",
                              padx=(7, 0), pady=0)
        else:
            self.cartes.grid_columnconfigure(0, weight=1, uniform="")
            self.cartes.grid_columnconfigure(1, weight=0, uniform="")
            self.dr_card.grid(row=0, column=0, columnspan=2, sticky="ew",
                              padx=0, pady=(0, 8))
            self.sr_card.grid(row=1, column=0, columnspan=2, sticky="ew",
                              padx=0, pady=0)

    def _construire_entete(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        head.grid_columnconfigure(0, weight=1)

        noms = ctk.CTkFrame(head, fg_color="transparent")
        noms.grid(row=0, column=0, sticky="w")
        self.name_label = ctk.CTkLabel(noms, text="Chargement…", font=self.f["title"],
                                       text_color=theme.TEXT, anchor="w")
        self.name_label.pack(anchor="w")
        self.stats_label = ctk.CTkLabel(noms, text="", font=self.f["small"],
                                        text_color=theme.TEXT_DIM, anchor="w")
        self.stats_label.pack(anchor="w", pady=(2, 0))

        self.refresh_btn = ctk.CTkButton(head, text="Actualiser", width=110, height=32,
                                         font=self.f["body"], corner_radius=8,
                                         fg_color=theme.ACCENT, hover_color=theme.ACCENT_HI,
                                         command=self.refresh)
        self.refresh_btn.grid(row=0, column=1, sticky="e")

    def _construire_bas(self):
        carte = Card(self)
        carte.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        carte.grid_columnconfigure(0, weight=1)
        carte.grid_rowconfigure(1, weight=1)

        barre = ctk.CTkFrame(carte, fg_color="transparent")
        barre.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 10))
        barre.grid_columnconfigure(1, weight=1)

        self.selecteur = ctk.CTkSegmentedButton(
            barre, values=[AMIS, COURSES], font=self.f["small"], height=30,
            corner_radius=8, command=self._changer_vue,
            selected_color=theme.ACCENT, selected_hover_color=theme.ACCENT_HI,
            unselected_color=theme.SURFACE_HI, unselected_hover_color=theme.BORDER,
            text_color=theme.TEXT)
        self.selecteur.grid(row=0, column=0, sticky="w")
        self.selecteur.set(AMIS)

        self.compteur = ctk.CTkLabel(barre, text="", font=self.f["tiny"],
                                     text_color=theme.TEXT_FAINT, anchor="e")
        self.compteur.grid(row=0, column=1, sticky="e")

        self.vue_amis = VueAmis(carte, self.f)
        self.vue_courses = VueCourses(carte, self.f, self.app.run_async,
                                      au_changement=self._maj_compteur)
        self.vue_amis.grid(row=1, column=0, sticky="nsew")

    # --- navigation entre les deux vues ---

    def _changer_vue(self, valeur):
        self.vue_amis.grid_forget()
        self.vue_courses.grid_forget()
        if valeur == COURSES:
            self.vue_courses.grid(row=1, column=0, sticky="nsew")
            self._maj_compteur(self.vue_courses.filtrees, self.vue_courses.affichees)
            if not self._courses_chargees:
                self._charger_courses()
        else:
            self.vue_amis.grid(row=1, column=0, sticky="nsew")
            self.compteur.configure(text="")

    def _maj_compteur(self, filtrees, affichees):
        if self.selecteur.get() == COURSES:
            self.compteur.configure(text=f"{affichees} affichée(s) sur {len(filtrees)}")

    # --- chargement ---

    def on_show(self):
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def refresh(self, force=False):
        self.refresh_btn.configure(state="disabled", text="…")
        self.app.set_status("Interrogation de raceos.gg…")
        self.app.run_async(
            lambda: ratings_core.load(self.ctx, with_friends=True, refresh=force),
            self._on_loaded, self._on_error)
        if self._courses_chargees:
            self._charger_courses()

    def _charger_courses(self):
        """Prepare le chargeur, la vue tire la premiere page toute seule.

        `ouvrir` retombe sur les courses en cache si le backend ne repond pas ;
        il ne leve que s'il n'y a rien du tout a montrer.
        """
        self._courses_chargees = True
        self.app.run_async(lambda: courses_core.ouvrir(self.ctx),
                           self.vue_courses.demarrer,
                           self.vue_courses.indisponible)

    def _on_error(self, exc):
        self.refresh_btn.configure(state="normal", text="Actualiser")
        self.name_label.configure(text="Indisponible")
        self.stats_label.configure(text=str(exc).replace("\n", " ").strip())
        self.app.set_status("Échec du chargement", error=True)

    def _on_loaded(self, data):
        self.refresh_btn.configure(state="normal", text="Actualiser")

        self.name_label.configure(text=data.name)
        stats = data.my_stats()
        if stats:
            races, wins = stats.get("races", 0), stats.get("wins", 0)
            taux = (wins / races * 100) if races else 0
            self.stats_label.configure(
                text=f"{races} courses · {wins} victoires ({taux:.1f} %)")

        if data.offline:
            self.banner_label.configure(
                text=f"Hors ligne — dernières valeurs connues, {local_time(data.fetched_at)}.\n"
                     "Relance Le Mans Ultimate puis Actualiser pour des valeurs fraîches.")
            self.banner.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        else:
            self.banner.grid_forget()

        dr, sr = data.driver_rank, data.safety_rank
        self.dr_card.update_rating(dr.get("rank", "?"), dr.get("tier", 0),
                                   dr.get("progress", 0.0), "ELO", dr.get("elo", 0.0),
                                   exact=bool(dr.get("elo")))

        contact = sr.get("contactImpactsPerLapRatio") or 0
        self.sr_card.update_rating(sr.get("rank", "?"), sr.get("tier", 0),
                                   sr.get("progress", 0.0), "Rating", sr.get("rating", 0.0),
                                   exact=bool(sr.get("rating")),
                                   extra=f"Contacts par tour {contact:.3f}" if contact else "")

        self.vue_amis.remplir(data)
        self.app.set_status(
            f"Hors ligne · {local_time(data.fetched_at)}" if data.offline else "À jour")
