"""Fenetre principale du hub."""

import threading
import tkinter

import customtkinter as ctk

from ..core import historique
from ..core.errors import HubError
from ..modules.base import Context
from . import responsive, theme
from .pages import discover

APP_NAME = "LMU Central"

# Barre laterale : largeur confortable, et largeur reduite quand la fenetre
# devient etroite — mieux vaut rogner le menu que le contenu.
SIDEBAR_W = 210
SIDEBAR_W_COMPACT = 156
SEUIL_SIDEBAR = 900

# Fonctionnalites annoncees mais pas encore disponibles.
ROADMAP = ["Overlays télémétrie", "Stratégie carburant"]


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self._appliquer_icone()
        self.geometry("1120x860")
        # Plancher volontairement bas : chaque page se replie au lieu de se
        # faire couper, il n'y a donc pas de raison d'interdire les petites
        # fenetres a qui veut garder le hub dans un coin de l'ecran.
        self.minsize(720, 520)
        self.configure(fg_color=theme.BG)

        self.f = theme.fonts()
        self.ctx = Context()
        self.pages = {}
        self.nav_buttons = {}
        self.current = None

        # Suivi des sessions de jeu, pour relever le rating en fin de course.
        self._en_session = False
        self._releve_attendu = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_content()
        self._build_statusbar()

        for page_cls in discover():
            self._add_page(page_cls)

        if self.pages:
            self.show(next(iter(self.pages)))

        self.protocol("WM_DELETE_WINDOW", self._fermer)
        self._poll_game_state()

    def _appliquer_icone(self):
        """Pose le logo sur la fenetre et dans la barre des taches.

        Sans cet appel, CustomTkinter installe la sienne — un carre bleu — et
        c'est elle qu'on voit partout. L'icone de l'executable, elle, ne sert
        qu'a l'explorateur de fichiers : la barre de titre lit celle que Tk
        porte, pas celle du .exe.
        """
        chemin = theme.chemin_icone()
        if chemin is None:
            return
        try:
            self.iconbitmap(str(chemin), default=str(chemin))
        except tkinter.TclError:
            pass

    # --- construction ---

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=SIDEBAR_W, corner_radius=0,
                                    fg_color=theme.SURFACE)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsw")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(1, weight=1)

        self.brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.brand.grid(row=0, column=0, sticky="ew", padx=16, pady=(22, 16))

        # Deux corps : le nom complet ne tient pas dans la barre retrecie.
        # Mesure faite : « LMU CENTRAL » sur une seule ligne ne rentrerait
        # qu'en corps 15, trop petit pour un logotype — d'ou l'empilement.
        self._polices_logo = {True: ctk.CTkFont(theme.FAMILY, 20, "bold"),
                              False: ctk.CTkFont(theme.FAMILY, 14, "bold")}
        self._image_logo = theme.charger_logo(32)

        self.logo_marque = ctk.CTkLabel(self.brand, text="", image=self._image_logo)
        self.logo_lmu = ctk.CTkLabel(self.brand, text="LMU", text_color=theme.ACCENT,
                                     anchor="w")
        self.logo_nom = ctk.CTkLabel(self.brand, text="CENTRAL", text_color=theme.TEXT,
                                     anchor="w")
        self._disposer_logo(True)

        # Le menu defile : le hub est fait pour accueillir d'autres pages, et
        # une fenetre courte ne doit pas en cacher. Tant que tout tient,
        # l'ascenseur est repeint couleur du fond plutot qu'affiche pour rien.
        self.nav = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent",
                                          scrollbar_button_color=theme.BORDER,
                                          scrollbar_button_hover_color=theme.TEXT_FAINT)
        self.nav.grid(row=1, column=0, sticky="nsew", padx=6)
        self.nav.grid_columnconfigure(0, weight=1)
        responsive.ascenseur_discret(self.nav, theme.SURFACE)

        soon = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        soon.grid(row=2, column=0, sticky="ew", padx=20, pady=(8, 16))
        ctk.CTkLabel(soon, text="À VENIR", font=self.f["tiny"],
                     text_color=theme.TEXT_FAINT).pack(anchor="w", pady=(0, 4))
        for item in ROADMAP:
            ctk.CTkLabel(soon, text=item, font=self.f["tiny"],
                         text_color=theme.TEXT_FAINT).pack(anchor="w")

        responsive.suivre_paliers(self, (SEUIL_SIDEBAR,), self._ajuster_sidebar)

    def _disposer_logo(self, large):
        """Ajuste la taille du logotype a la largeur de la barre.

        La barre a une largeur fixe : ce qui depasse est coupe net, sans
        defilement possible. La marque et l'empilement sur deux lignes ne
        changent pas, seuls les corps et la taille de l'image suivent.
        """
        police = self._polices_logo[bool(large)]
        self.logo_lmu.configure(font=police)
        self.logo_nom.configure(font=police)
        if self._image_logo is not None:
            cote = 32 if large else 24
            self._image_logo.configure(size=(cote, cote))

        self.logo_marque.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 10))
        self.logo_lmu.grid(row=0, column=1, sticky="w", pady=0)
        self.logo_nom.grid(row=1, column=1, sticky="w", pady=0)

    def _ajuster_sidebar(self, palier):
        """Menu et marges se resserrent pour laisser la place au contenu."""
        self.sidebar.configure(width=SIDEBAR_W if palier else SIDEBAR_W_COMPACT)
        self._disposer_logo(bool(palier))
        contenu = getattr(self, "content", None)
        if contenu is not None:
            contenu.grid_configure(padx=24 if palier else 12)

    def _build_content(self):
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=24, pady=(22, 10))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, height=32, corner_radius=0, fg_color=theme.SURFACE)
        bar.grid(row=1, column=1, sticky="sew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(1, weight=1)

        self.game_label = ctk.CTkLabel(bar, text="", font=self.f["tiny"],
                                       text_color=theme.TEXT_DIM, anchor="w")
        self.game_label.grid(row=0, column=0, sticky="w", padx=(16, 0))

        self.status_label = ctk.CTkLabel(bar, text="", font=self.f["tiny"],
                                         text_color=theme.TEXT_FAINT, anchor="e")
        self.status_label.grid(row=0, column=1, sticky="e", padx=(0, 16))

    def _add_page(self, page_cls):
        page = page_cls(self.content, self)
        self.pages[page_cls.name] = page

        btn = ctk.CTkButton(
            self.nav, text=page_cls.title, anchor="w", height=38,
            corner_radius=8, font=self.f["body"],
            fg_color="transparent", text_color=theme.TEXT_DIM,
            hover_color=theme.SURFACE_HI,
            command=lambda n=page_cls.name: self.show(n))
        btn.grid(row=len(self.nav_buttons), column=0, sticky="ew", pady=2)
        self.nav_buttons[page_cls.name] = btn

    # --- navigation ---

    def show(self, name):
        if self.current == name:
            return
        for page in self.pages.values():
            page.grid_forget()
        for key, btn in self.nav_buttons.items():
            active = key == name
            btn.configure(fg_color=theme.SURFACE_HI if active else "transparent",
                          text_color=theme.TEXT if active else theme.TEXT_DIM)
        page = self.pages[name]
        page.grid(row=0, column=0, sticky="nsew")
        self.current = name
        page.on_show()

    # --- utilitaires ---

    def set_status(self, text, error=False):
        self.status_label.configure(
            text=text, text_color=theme.ACCENT if error else theme.TEXT_FAINT)

    def run_async(self, work, on_done, on_error=None):
        """Execute `work` hors du thread graphique, puis revient dessus."""

        def revenir(action):
            """Repasse sur le thread graphique, sauf si la fenetre a disparu.

            Une tache lancee juste avant la fermeture se termine apres coup :
            `after` leverait alors une erreur dans un thread invisible.
            """
            try:
                self.after(0, action)
            except RuntimeError:
                pass

        def runner():
            try:
                result = work()
            except Exception as exc:  # remonte a l'appelant sans figer l'interface
                revenir(lambda e=exc: (on_error or self._report)(e))
                return
            revenir(lambda r=result: on_done(r))

        threading.Thread(target=runner, daemon=True).start()

    def _fermer(self):
        """Laisse chaque page liberer ses ressources avant de quitter."""
        for page in self.pages.values():
            try:
                page.on_close()
            except Exception as exc:
                print("fermeture de page:", exc)
        self.destroy()

    def _report(self, exc):
        self.set_status(str(exc).replace("\n", " ")[:120], error=True)

    def _poll_game_state(self):
        """Rafraichit l'indicateur d'etat du jeu, sans bloquer l'interface."""

        def check():
            try:
                etat = self.ctx.local.game_state()
                en_session = etat.get("status") != "unavailable"
                ou = etat.get("gameState") or etat.get("status") or "?"
                return True, en_session, ou
            except HubError:
                return False, False, None

        def done(resultat):
            lance, en_session, ou = resultat
            if lance:
                detail = "en session" if en_session else "menus"
                self.game_label.configure(text=f"● Le Mans Ultimate — {detail} ({ou})",
                                          text_color=theme.OK)
            else:
                self.game_label.configure(text="● Le Mans Ultimate — ferme",
                                          text_color=theme.TEXT_FAINT)

            # Sortie de session : une course vient de se terminer.
            if self._en_session and not en_session:
                self._planifier_releves()
            self._en_session = en_session

            self.after(15000, self._poll_game_state)

        self.run_async(check, done, lambda exc: self.after(15000, self._poll_game_state))

    # --- releve automatique du rating ---

    def _planifier_releves(self):
        """Le backend met quelques instants a publier le nouveau rating.

        On retente donc plusieurs fois apres la fin de course, et on s'arrete
        des qu'une valeur differente est relevee.
        """
        self._releve_attendu = True
        self.set_status("Course terminee — relevé du rating en attente…")
        for delai in (45_000, 120_000, 300_000):
            self.after(delai, self._tenter_releve)

    def _tenter_releve(self):
        if not self._releve_attendu:
            return
        self.run_async(lambda: historique.relever(self.ctx),
                       self._releve_fait, lambda exc: None)

    def _releve_fait(self, point):
        if not point:
            return
        self._releve_attendu = False
        self.set_status(
            f"Rating relevé : {point['drRank']} {point['drTier']} "
            f"{point['drProgress']:.2f} %")
        page = self.pages.get("ratings")
        if page is not None and getattr(page, "_loaded", False):
            page.refresh()


def run():
    theme.apply()
    App().mainloop()
