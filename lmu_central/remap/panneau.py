"""
Interface de gestion du remap des molettes crantees (volant Fanatec).

Permet de :
- demarrer / arreter le remap
- afficher ou masquer l'overlay
- modifier les libelles et les actions de chaque position
- detecter les boutons du volant sans passer par un script de diagnostic
- envoyer une action a la demande, pour la binder dans une appli tierce

Chaque molette a son onglet. Une position declenche une combinaison clavier,
qu'il suffit ensuite de binder dans le jeu ou l'application visee.

Integre au hub comme une page.

Une reserve : Windows interdit a un processus non-eleve d'injecter des frappes
vers un processus eleve. Pour viser Le Mans Ultimate lui-meme (lance par
EasyAntiCheat), il faut donc demarrer le hub en administrateur. Les autres
applications — Voicemod, Discord, OBS — se contentent d'un lancement normal.
"""

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
import keyboard
import pygame

from ..gui import responsive
from ..gui import theme as ui
from ..gui.widgets import Card
from . import config as cfg
from . import moteur as mot

INTERVALLE_POLL = 8  # millisecondes

# Largeurs en dessous desquelles on replie plutot que de laisser couper :
# le tableau des positions passe sur une colonne, la barre sur deux lignes.
SEUIL_DEUX_COLONNES = 830
SEUIL_BARRE = 560

COULEUR_OK = ui.OK
COULEUR_ERREUR = ui.ACCENT
COULEUR_NEUTRE = ui.TEXT_DIM

LIBELLES_BOUTONS = {
    "increment": "Molette +",
    "decrement": "Molette -",
    "confirm": "Confirmation",
}

# Touches considerees comme des modificateurs lors de la capture d'un raccourci :
# elles n'achevent pas la saisie, elles s'accumulent en prefixe.
MODIFICATEURS = {
    "ctrl": "ctrl", "left ctrl": "ctrl", "right ctrl": "ctrl",
    "shift": "shift", "left shift": "shift", "right shift": "shift",
    "alt": "alt", "left alt": "alt", "right alt": "alt", "alt gr": "alt",
    "windows": "windows", "left windows": "windows", "right windows": "windows",
}
ORDRE_MODIFICATEURS = ["ctrl", "shift", "alt", "windows"]


class PanneauRemap(ctk.CTkFrame):
    """Interface de remap des molettes, integrable dans une fenetre hote.

    Les 12 positions sont disposees en deux colonnes de six : la page tient
    ainsi dans la fenetre sans defilement.
    """

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")

        self.config_app = cfg.charger()
        self.moteur = mot.Moteur(self.config_app)
        self.overlay = None
        self.capture_en_cours = None
        self.capture_touches = None
        self.test_en_cours = None

        self.f = {
            "titre": ctk.CTkFont(ui.FAMILY, 13, "bold"),
            "corps": ctk.CTkFont(ui.FAMILY, 12),
            "petit": ctk.CTkFont(ui.FAMILY, 11),
            "mono": ctk.CTkFont(ui.mono_family(), 13),
            "mono_gras": ctk.CTkFont(ui.mono_family(), 13, "bold"),
        }

        # Widgets indexes par molette
        self.lignes = {}
        self.labels_bouton = {}
        self.labels_position = {}
        self.cartes_tableau = {}
        self.grilles = {}
        self.interrupteurs = []

        # Disposition courante, ajustee a la largeur reelle de la fenetre.
        self._colonnes_tableau = 2
        self._barre_large = True

        self._construire()
        self._rafraichir_etat_volant()

        self.after(INTERVALLE_POLL, self._boucle)

    # -- construction de l'interface ----------------------------------------

    def _construire(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._construire_barre()

        barre_onglets = ctk.CTkFrame(self, fg_color="transparent")
        barre_onglets.grid(row=1, column=0, sticky="w", pady=(10, 8))

        conteneur = ctk.CTkFrame(self, fg_color="transparent")
        conteneur.grid(row=2, column=0, sticky="nsew")
        conteneur.grid_columnconfigure(0, weight=1)
        conteneur.grid_rowconfigure(0, weight=1)

        self.onglets = []
        self.pages = []

        for indice, molette in enumerate(self.config_app["molettes"]):
            self.lignes[indice] = {}
            bouton = ctk.CTkButton(
                barre_onglets, text=molette["nom"], width=118, height=32,
                corner_radius=8, font=self.f["corps"],
                command=lambda i=indice: self._afficher_page(i))
            bouton.grid(row=0, column=indice, padx=(0, 6))
            self.onglets.append(bouton)

            page = ctk.CTkFrame(conteneur, fg_color="transparent")
            page.grid_columnconfigure(0, weight=1)
            self.pages.append(page)
            self._construire_onglet(page, indice)

        self._afficher_page(0)
        responsive.suivre_paliers(self, (SEUIL_BARRE, SEUIL_DEUX_COLONNES),
                                  self._changer_disposition)

    def _changer_disposition(self, palier):
        """Replie ou deplie l'interface selon la largeur disponible.

        Le tableau se redessine : on s'abstient tant qu'une capture ou un
        envoi est en cours, pour ne pas detruire le bouton qui les porte.
        """
        if self.capture_en_cours or self.capture_touches or self.test_en_cours:
            return

        large = palier >= 1
        if large != self._barre_large:
            self._barre_large = large
            self._replier_barre(large)

        colonnes = 2 if palier >= 2 else 1
        if colonnes != self._colonnes_tableau:
            self._colonnes_tableau = colonnes
            for indice in list(self.cartes_tableau):
                self._peupler_tableau(indice)

    def _afficher_page(self, actif):
        for indice, (bouton, page) in enumerate(zip(self.onglets, self.pages)):
            if indice == actif:
                bouton.configure(fg_color=ui.ACCENT, hover_color=ui.ACCENT_HI,
                                 text_color=ui.TEXT)
                page.grid(row=0, column=0, sticky="nsew")
            else:
                bouton.configure(fg_color=ui.SURFACE_HI, hover_color=ui.BORDER,
                                 text_color=ui.TEXT_DIM)
                page.grid_forget()

    def _construire_barre(self):
        carte = Card(self)
        carte.grid(row=0, column=0, sticky="ew")
        carte.grid_columnconfigure(1, weight=1)

        # Ligne 1 : commandes
        gauche = ctk.CTkFrame(carte, fg_color="transparent")
        gauche.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 0))

        self.bouton_demarrer = ctk.CTkButton(
            gauche, text="Demarrer", width=104, height=32, corner_radius=8,
            font=self.f["corps"], fg_color=ui.ACCENT, hover_color=ui.ACCENT_HI,
            command=self._basculer_moteur)
        self.bouton_demarrer.grid(row=0, column=0)

        self.var_overlay = tk.BooleanVar(value=self.config_app["overlay"]["affiche"])
        self.var_compact = tk.BooleanVar(value=self.config_app["overlay"]["compact"])
        self.var_traversant = tk.BooleanVar(
            value=self.config_app["overlay"]["clic_traversant"])

        interrupteurs = (
            ("Overlay", self.var_overlay, self._basculer_overlay),
            ("Compact", self.var_compact, self._changer_compact),
            ("Clic traversant", self.var_traversant, self._changer_traversant),
        )
        for libelle, variable, commande in interrupteurs:
            self.interrupteurs.append(ctk.CTkSwitch(
                gauche, text=libelle, variable=variable, command=commande,
                font=self.f["corps"], switch_width=38, switch_height=18,
                progress_color=ui.ACCENT, text_color=ui.TEXT_DIM))

        self.label_etat = ctk.CTkLabel(carte, text="Arrete", font=self.f["corps"],
                                       text_color=COULEUR_NEUTRE)

        # Ligne 2 : positions courantes et volant detecte
        self.positions = ctk.CTkFrame(carte, fg_color="transparent")
        self.positions.grid(row=1, column=0, sticky="w", padx=16, pady=(6, 12))

        for indice, molette in enumerate(self.config_app["molettes"]):
            self.labels_position[indice] = ctk.CTkLabel(
                self.positions, text=molette["nom"] + " : -",
                font=self.f["mono_gras"], text_color=ui.TEXT, anchor="w")

        self.label_volant = ctk.CTkLabel(carte, text="", font=self.f["petit"],
                                         text_color=COULEUR_NEUTRE)
        self._replier_barre(True)

    def _replier_barre(self, large):
        """Commandes sur une ligne, ou repliees sur plusieurs si c'est etroit.

        Les interrupteurs et l'etat tiennent a droite du bouton Demarrer tant
        qu'il y a la place ; sinon ils passent dessous, ou ils restent lisibles
        au lieu d'etre coupes par le bord de la fenetre.
        """
        for indice, label in self.labels_position.items():
            label.grid(row=0 if large else indice, column=indice if large else 0,
                       sticky="w", padx=(0, 20) if large else 0,
                       pady=0 if large else (0, 2))

        if large:
            for colonne, interrupteur in enumerate(self.interrupteurs, 1):
                interrupteur.grid(row=0, column=colonne, padx=(18, 0), pady=0)
            self.label_etat.configure(anchor="e")
            self.label_etat.grid(row=0, column=1, sticky="e", padx=16, pady=(12, 0))
            self.label_volant.configure(anchor="e")
            self.label_volant.grid(row=1, column=1, sticky="e", padx=16, pady=(6, 12))
            return

        for colonne, interrupteur in enumerate(self.interrupteurs):
            interrupteur.grid(row=1, column=colonne, padx=(0, 16), pady=(10, 0))
        self.label_etat.configure(anchor="w")
        self.label_etat.grid(row=2, column=0, columnspan=2, sticky="w",
                             padx=16, pady=(8, 0))
        self.label_volant.configure(anchor="w")
        self.label_volant.grid(row=3, column=0, columnspan=2, sticky="w",
                               padx=16, pady=(2, 12))

    def _construire_onglet(self, parent, indice):
        parent.grid_rowconfigure(0, weight=1)
        self._construire_tableau(parent, indice)
        self._construire_boutons_volant(parent, indice)

    def _construire_tableau(self, parent, indice):
        carte = Card(parent)
        carte.grid(row=0, column=0, sticky="nsew")
        self.cartes_tableau[indice] = carte

        ctk.CTkLabel(carte, text="ACTIONS PAR POSITION", font=self.f["titre"],
                     text_color=ui.TEXT_FAINT, anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(14, 2))
        explication = ctk.CTkLabel(
            carte,
            text="Le libelle s'affiche dans l'overlay. Binder : mets l'appli en "
                 "attente d'une touche, clique sur Envoyer, puis bascule dessus.",
            font=self.f["petit"], text_color=ui.TEXT_FAINT,
            anchor="w", justify="left")
        explication.grid(row=1, column=0, columnspan=2, sticky="ew", padx=18,
                         pady=(0, 10))
        responsive.replier_texte(explication, self, marge=44)

        self._peupler_tableau(indice)

    def _peupler_tableau(self, indice):
        """(Re)dessine les positions sur une ou deux colonnes.

        Les StringVar sont conservees d'une disposition a l'autre : seules les
        cases sont recreees, donc une saisie en cours n'est pas perdue.
        """
        carte = self.cartes_tableau[indice]
        for grille in self.grilles.pop(indice, []):
            grille.destroy()

        colonnes = self._colonnes_tableau
        for colonne in range(2):
            carte.grid_columnconfigure(colonne, weight=1 if colonne < colonnes else 0,
                                       uniform="col" if colonnes > 1 else "")

        total = self.config_app["molettes"][indice]["nb_positions"]
        par_colonne = (total + colonnes - 1) // colonnes

        entetes = (("POS", 0, 26), ("LIBELLE", 1, 118), ("RACCOURCI", 2, 102),
                   ("", 3, 56), ("", 4, 66))

        grilles = []
        for colonne in range(colonnes):
            grille = ctk.CTkFrame(carte, fg_color="transparent")
            if colonnes == 1:
                marges = (18, 18)
            else:
                marges = (18, 9) if colonne == 0 else (9, 18)
            grille.grid(row=2, column=colonne, sticky="new", padx=marges, pady=(0, 12))
            grilles.append(grille)

            for titre, col, largeur in entetes:
                # Libelle et raccourci s'etirent : la place en plus leur profite.
                grille.grid_columnconfigure(col, minsize=largeur,
                                            weight=1 if col in (1, 2) else 0)
                if titre:
                    ctk.CTkLabel(grille, text=titre, font=self.f["petit"],
                                 text_color=ui.TEXT_FAINT, anchor="w").grid(
                        row=0, column=col, sticky="ew", padx=(0, 4), pady=(0, 4))

            debut = colonne * par_colonne + 1
            fin = min(debut + par_colonne, total + 1)
            for rang, position in enumerate(range(debut, fin), 1):
                self._construire_ligne(grille, indice, position, rang)

        self.grilles[indice] = grilles

    def _construire_ligne(self, parent, indice, position, rang):
        action = self.config_app["molettes"][indice]["actions"][str(position)]
        ligne = self.lignes[indice].setdefault(position, {})

        ctk.CTkLabel(parent, text=str(position), font=self.f["mono"],
                     text_color=ui.TEXT_DIM, anchor="w", width=26).grid(
            row=rang, column=0, sticky="w", pady=1)

        var_libelle = self._variable(
            ligne, "libelle", action["libelle"],
            lambda *_, i=indice, p=position: self._changer_libelle(i, p))
        ctk.CTkEntry(parent, textvariable=var_libelle, width=118, height=26,
                     corner_radius=6, font=self.f["corps"], border_width=1,
                     fg_color=ui.BG, border_color=ui.BORDER,
                     text_color=ui.TEXT).grid(
            row=rang, column=1, sticky="ew", padx=(0, 6), pady=1)

        var_touches = self._variable(
            ligne, "touches", action["touches"],
            lambda *_, i=indice, p=position: self._changer_touches(i, p))
        ctk.CTkEntry(parent, textvariable=var_touches, width=102, height=26,
                     corner_radius=6, font=self.f["mono"], border_width=1,
                     fg_color=ui.BG, border_color=ui.BORDER,
                     text_color=ui.TEXT).grid(
            row=rang, column=2, sticky="ew", padx=(0, 6), pady=1)

        bouton_capture = ctk.CTkButton(
            parent, text="Saisir", width=56, height=26, corner_radius=6,
            font=self.f["petit"], fg_color=ui.SURFACE_HI, hover_color=ui.BORDER,
            text_color=ui.TEXT_DIM,
            command=lambda i=indice, p=position: self._capturer_touches(i, p))
        bouton_capture.grid(row=rang, column=3, padx=(0, 6), pady=1)

        bouton_test = ctk.CTkButton(
            parent, text="Envoyer", width=66, height=26, corner_radius=6,
            font=self.f["petit"], fg_color=ui.SURFACE_HI, hover_color=ui.BORDER,
            text_color=ui.TEXT_DIM,
            command=lambda i=indice, p=position: self._tester(i, p))
        bouton_test.grid(row=rang, column=4, pady=1)

        ligne["bouton_capture"] = bouton_capture
        ligne["bouton_test"] = bouton_test

    @staticmethod
    def _variable(ligne, cle, valeur, rappel):
        """StringVar d'une case, creee une seule fois.

        Le tableau se redessine quand la fenetre change de largeur : recreer
        les variables a chaque fois empilerait les observateurs, et chaque
        frappe declencherait autant d'ecritures du fichier de configuration.
        """
        if cle not in ligne:
            variable = tk.StringVar(value=valeur)
            variable.trace_add("write", rappel)
            ligne[cle] = variable
        return ligne[cle]

    def _construire_boutons_volant(self, parent, indice):
        carte = Card(parent)
        carte.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        carte.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(carte, text="BOUTONS DU VOLANT", font=self.f["titre"],
                     text_color=ui.TEXT_FAINT, anchor="w").grid(
            row=0, column=0, columnspan=4, sticky="ew", padx=18, pady=(12, 2))
        aide = ctk.CTkLabel(
            carte,
            text="Clique sur Detecter puis actionne le bouton voulu sur le volant.",
            font=self.f["petit"], text_color=ui.TEXT_FAINT, anchor="w",
            justify="left")
        aide.grid(row=1, column=0, columnspan=4, sticky="ew", padx=18, pady=(0, 10))
        responsive.replier_texte(aide, self, marge=44)

        self.labels_bouton[indice] = {}
        boutons = self.config_app["molettes"][indice]["boutons"]

        for colonne, (cle, titre) in enumerate(LIBELLES_BOUTONS.items()):
            bloc = ctk.CTkFrame(carte, fg_color="transparent")
            bloc.grid(row=2, column=colonne, sticky="w",
                      padx=(18 if colonne == 0 else 0, 24), pady=(0, 12))

            ctk.CTkLabel(bloc, text=titre, font=self.f["petit"],
                         text_color=ui.TEXT_DIM, anchor="w").grid(row=0, column=0,
                                                                  sticky="w")
            label = ctk.CTkLabel(bloc, text=self._texte_bouton(boutons[cle]),
                                 font=self.f["mono_gras"], text_color=ui.TEXT,
                                 anchor="w")
            label.grid(row=1, column=0, sticky="w", pady=(1, 5))
            self.labels_bouton[indice][cle] = label

            ctk.CTkButton(bloc, text="Detecter", width=84, height=28, corner_radius=6,
                          font=self.f["petit"], fg_color=ui.SURFACE_HI,
                          hover_color=ui.BORDER, text_color=ui.TEXT_DIM,
                          command=lambda i=indice, c=cle: self._detecter(i, c)).grid(
                row=2, column=0, sticky="w")

        ctk.CTkButton(carte, text="Position → 1", width=110, height=28,
                      corner_radius=6, font=self.f["petit"], fg_color=ui.SURFACE_HI,
                      hover_color=ui.BORDER, text_color=ui.TEXT_DIM,
                      command=lambda i=indice: self._resynchroniser(i)).grid(
            row=2, column=3, sticky="sw", pady=(0, 12))

    @staticmethod
    def _texte_bouton(valeur):
        return "bouton " + str(valeur) if valeur is not None else "non defini"

    # -- moteur --------------------------------------------------------------

    def _basculer_moteur(self):
        if self.moteur.actif:
            self.moteur.arreter()
            self._fermer_overlay()
            self.bouton_demarrer.configure(text="Demarrer")
            self.label_etat.configure(text="Arrete", text_color=COULEUR_NEUTRE)
            for indice, molette in enumerate(self.config_app["molettes"]):
                self.labels_position[indice].configure(text=f"{molette['nom']} : -")
            return

        collisions = self.moteur.collisions_touches()
        if collisions:
            messagebox.showwarning(
                "Raccourcis en double",
                "Ces combinaisons sont utilisees par plusieurs positions :\n\n"
                f"{', '.join(collisions)}\n\n"
                "Elles declencheront la meme action. Verifie tes saisies.",
            )

        ok, message = self.moteur.demarrer()
        if not ok:
            self.label_etat.configure(text="Erreur", text_color=COULEUR_ERREUR)
            messagebox.showerror("Demarrage impossible", message)
            return

        self.bouton_demarrer.configure(text="Arreter")
        self.label_etat.configure(text=message, text_color=COULEUR_OK)
        for molette in self.moteur.molettes:
            if molette.active:
                self._maj_position(molette.indice, molette.position)

        if self.var_overlay.get():
            self._ouvrir_overlay()

    def _resynchroniser(self, indice):
        molette = self.moteur.molettes[indice]
        molette.position = molette.config["position_reset"]
        self._maj_position(indice, molette.position)

    def _boucle(self):
        for evenement in self.moteur.poll():
            if evenement[0] == "position":
                self._maj_position(evenement[1], evenement[2])
            elif evenement[0] == "action":
                nom = self.config_app["molettes"][evenement[1]]["nom"]
                self.label_etat.configure(text=f"{nom} -> {evenement[3]}",
                                          text_color=COULEUR_OK)
            elif evenement[0] == "erreur":
                self.label_etat.configure(text=evenement[1], text_color=COULEUR_ERREUR)
                self.bouton_demarrer.configure(text="Demarrer")
                self._fermer_overlay()

        if self.capture_en_cours:
            self._poll_capture()

        self.after(INTERVALLE_POLL, self._boucle)

    def _maj_position(self, indice, position):
        molette = self.config_app["molettes"][indice]
        libelle = molette["actions"][str(position)]["libelle"]
        self.labels_position[indice].configure(
            text=f"{molette['nom']} : {position} - {libelle}")
        if self.overlay is not None:
            self.overlay.maj(indice, position)

    # -- overlay -------------------------------------------------------------

    def _basculer_overlay(self):
        self.config_app["overlay"]["affiche"] = self.var_overlay.get()
        self._sauver()

        if self.var_overlay.get():
            if self.moteur.actif:
                self._ouvrir_overlay()
        else:
            self._fermer_overlay()

    def _changer_traversant(self):
        self.config_app["overlay"]["clic_traversant"] = self.var_traversant.get()
        self._sauver()
        self._reconstruire_overlay()

    def _changer_compact(self):
        self.config_app["overlay"]["compact"] = self.var_compact.get()
        self._sauver()
        self._reconstruire_overlay()

    def _reconstruire_overlay(self):
        """L'overlay se construit d'un bloc : on le recree pour l'appliquer."""
        if self.overlay is not None:
            self._fermer_overlay()
            self._ouvrir_overlay()

    def _ouvrir_overlay(self):
        if self.overlay is not None:
            return
        self.overlay = mot.Overlay(self.winfo_toplevel(), self.config_app, au_deplacement=self._sauver)
        for molette in self.moteur.molettes:
            if molette.active:
                self.overlay.maj(molette.indice, molette.position)

    def _fermer_overlay(self):
        if self.overlay is not None:
            self.overlay.destroy()
            self.overlay = None

    # -- edition de la configuration ----------------------------------------

    def _action(self, indice, position):
        return self.config_app["molettes"][indice]["actions"][str(position)]

    def _changer_libelle(self, indice, position):
        self._action(indice, position)["libelle"] = \
            self.lignes[indice][position]["libelle"].get()
        if self.overlay is not None:
            self.overlay.rafraichir()
        if self.moteur.actif and self.moteur.molettes[indice].position == position:
            self._maj_position(indice, position)
        self._sauver()

    def _changer_touches(self, indice, position):
        self._action(indice, position)["touches"] = \
            self.lignes[indice][position]["touches"].get()
        self._sauver()

    def _sauver(self):
        cfg.sauver(self.config_app)

    # -- capture d'un raccourci clavier -------------------------------------

    def _capturer_touches(self, indice, position):
        """Ecoute le clavier et remplit le champ avec la combinaison tapee."""
        if self.capture_touches:
            memes = (self.capture_touches["indice"] == indice
                     and self.capture_touches["position"] == position)
            self._arreter_capture_touches()
            if memes:
                return

        self.capture_touches = {
            "indice": indice,
            "position": position,
            "modificateurs": [],
            "hook": None,
        }
        self.lignes[indice][position]["bouton_capture"].configure(text="...")
        self.label_etat.configure(
            text="Tape la combinaison voulue (Echap pour annuler)",
            text_color=COULEUR_ERREUR,
        )
        self.capture_touches["hook"] = keyboard.hook(self._sur_touche_capturee)

    def _sur_touche_capturee(self, evenement):
        """Appele depuis le thread du hook clavier : on repasse dans Tk."""
        if not self.capture_touches or evenement.event_type != "down":
            return
        self.after(0, lambda nom=evenement.name: self._traiter_touche(nom))

    def _traiter_touche(self, nom):
        if not self.capture_touches or nom is None:
            return

        if nom == "esc":
            self._arreter_capture_touches()
            self.label_etat.configure(text="Saisie annulee", text_color=COULEUR_NEUTRE)
            return

        # Un modificateur ne termine pas la saisie : il s'accumule en prefixe.
        if nom in MODIFICATEURS:
            canonique = MODIFICATEURS[nom]
            if canonique not in self.capture_touches["modificateurs"]:
                self.capture_touches["modificateurs"].append(canonique)
            return

        modificateurs = [m for m in ORDRE_MODIFICATEURS
                         if m in self.capture_touches["modificateurs"]]
        combinaison = "+".join(modificateurs + [nom])

        indice = self.capture_touches["indice"]
        position = self.capture_touches["position"]
        self._arreter_capture_touches()

        self.lignes[indice][position]["touches"].set(combinaison)
        self.label_etat.configure(text=f"Raccourci : {combinaison}",
                                  text_color=COULEUR_OK)

    def _arreter_capture_touches(self):
        if not self.capture_touches:
            return
        if self.capture_touches["hook"] is not None:
            try:
                keyboard.unhook(self.capture_touches["hook"])
            except (KeyError, ValueError):
                pass
        indice = self.capture_touches["indice"]
        position = self.capture_touches["position"]
        self.capture_touches = None
        self.lignes[indice][position]["bouton_capture"].configure(text="Saisir")

    # -- envoi manuel, pour binder dans une appli tierce ---------------------

    def _tester(self, indice, position):
        """Envoie l'action apres un compte a rebours.

        Laisse le temps de basculer sur l'appli qui attend une touche ou un
        bouton (Voicemod, Discord, le menu controles d'un jeu...).
        """
        if self.test_en_cours:
            self._annuler_test()
            return

        action = self._action(indice, position)

        if not action["touches"]:
            messagebox.showinfo(
                "Aucune touche definie",
                "Saisis la combinaison a envoyer (ex: ctrl+alt+f1) avant de tester.",
            )
            return

        self.test_en_cours = {
            "indice": indice,
            "position": position,
            "restant": int(self.config_app["delai_test"]),
        }
        self.lignes[indice][position]["bouton_test"].configure(text="Annuler")
        self._tic_test()

    def _tic_test(self):
        if not self.test_en_cours:
            return

        restant = self.test_en_cours["restant"]
        indice = self.test_en_cours["indice"]
        position = self.test_en_cours["position"]

        if restant <= 0:
            libelle = self.moteur.molettes[indice].declencher(position)
            self._annuler_test()
            self.label_etat.configure(text=f"Envoye : {libelle}", text_color=COULEUR_OK)
            return

        self.label_etat.configure(
            text=f"Bascule sur l'appli... envoi dans {restant}",
            text_color=COULEUR_ERREUR,
        )
        self.test_en_cours["restant"] = restant - 1
        self.after(1000, self._tic_test)

    def _annuler_test(self):
        if not self.test_en_cours:
            return
        indice = self.test_en_cours["indice"]
        position = self.test_en_cours["position"]
        self.test_en_cours = None
        self.lignes[indice][position]["bouton_test"].configure(text="Envoyer")
        self.label_etat.configure(text="Pret", text_color=COULEUR_NEUTRE)

    # -- detection des boutons du volant ------------------------------------

    def _detecter(self, indice, cle):
        # Un second clic annule la detection en cours.
        if self.capture_en_cours:
            memes = (self.capture_en_cours["indice"] == indice
                     and self.capture_en_cours["cle"] == cle)
            self.capture_en_cours = None
            self._rafraichir_labels_boutons()
            if memes:
                return

        if self.moteur.actif:
            messagebox.showinfo(
                "Arrete le remap d'abord",
                "La detection lit directement le volant. Arrete le remap, "
                "puis relance la detection.",
            )
            return

        # On ecoute TOUS les joysticks : le volant n'est pas forcement le
        # premier peripherique enumere par pygame.
        joysticks = mot.ouvrir_tous()
        if not joysticks:
            messagebox.showerror("Volant introuvable",
                                 "Aucun joystick detecte. Verifie le branchement.")
            return

        pygame.event.pump()
        self.capture_en_cours = {
            "indice": indice,
            "cle": cle,
            "joysticks": joysticks,
            "base": {
                js.get_instance_id(): [js.get_button(i) for i in range(js.get_numbuttons())]
                for js in joysticks
            },
        }
        self.labels_bouton[indice][cle].configure(text="APPUIE...",
                                                  text_color=COULEUR_ERREUR)
        self.label_etat.configure(
            text="Actionne le bouton a associer (re-clique pour annuler)",
            text_color=COULEUR_ERREUR,
        )

    def _poll_capture(self):
        capture = self.capture_en_cours

        try:
            pygame.event.pump()
            for js in capture["joysticks"]:
                base = capture["base"][js.get_instance_id()]
                for i in range(js.get_numbuttons()):
                    # On ignore les boutons deja enfonces au lancement de la capture.
                    if js.get_button(i) and not base[i]:
                        self._valider_capture(capture["indice"], capture["cle"], i)
                        return
        except pygame.error:
            self.capture_en_cours = None
            self._rafraichir_labels_boutons()

    def _valider_capture(self, indice, cle, index):
        self.config_app["molettes"][indice]["boutons"][cle] = index
        self.capture_en_cours = None
        self.labels_bouton[indice][cle].configure(text=self._texte_bouton(index),
                                                  text_color=COULEUR_OK)
        self.label_etat.configure(text=f"Bouton {index} enregistre",
                                  text_color=COULEUR_OK)
        self._sauver()

    def _rafraichir_labels_boutons(self):
        for indice, labels in self.labels_bouton.items():
            boutons = self.config_app["molettes"][indice]["boutons"]
            for cle, label in labels.items():
                label.configure(text=self._texte_bouton(boutons[cle]),
                                text_color=COULEUR_NEUTRE)
        self.label_etat.configure(text="Detection annulee", text_color=COULEUR_NEUTRE)

    # -- divers --------------------------------------------------------------

    def _rafraichir_etat_volant(self):
        joysticks = mot.lister_joysticks()
        if joysticks:
            # Le volant n'est pas forcement le premier enumere : on retient
            # celui qui a le plus de boutons.
            _, nom, nb = max(joysticks, key=lambda j: j[2])
            suffixe = f" (+{len(joysticks) - 1} autre(s))" if len(joysticks) > 1 else ""
            self.label_volant.configure(text=f"{nom} ({nb} boutons){suffixe}")
        else:
            self.label_volant.configure(text="aucun volant detecte")

    def fermer(self):
        """Libere le volant, l'overlay et la capture clavier."""
        self._arreter_capture_touches()
        self._sauver()
        self.moteur.arreter()
        self._fermer_overlay()
