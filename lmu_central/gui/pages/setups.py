"""Page Setups : consulter et comparer ses reglages, jeu ferme.

Deux panneaux. A gauche la collection, filtrable par circuit, par voiture et
par categorie ; a droite le setup choisi, mis en forme comme le garage du jeu.
Epingler un premier setup puis en choisir un second bascule le panneau de
droite en comparaison. « Voir dans le dossier » ouvre l'Explorateur sur le
fichier du setup choisi.

Choisir un circuit seul regroupe la liste par voiture — la question qu'on se
pose en arrivant sur un circuit est « qu'est-ce que j'ai ici, et pour quelle
voiture ». Choisir une voiture seule regroupe par circuit, pour la raison
inverse. Les deux ensemble, ou aucun des deux, laissent la liste a plat.

La fenetre etroite montre un panneau a la fois, avec un retour vers la liste :
serrer les deux rendrait le tableau de valeurs illisible, et les empiler ne
laisserait a chacun que deux cents pixels de hauteur.
"""

import os

import customtkinter as ctk

from ...core import explorateur
from ...core import setups as st
from ...core.errors import HubError
from .. import responsive, theme
from ..widgets import Card, tronquer
from .base import Page

# critere -> libelle du choix « pas de filtre », dans l'ordre des menus.
FILTRES = (("circuit", "Tous les circuits"),
           ("voiture", "Toutes les voitures"),
           ("categorie", "Toutes les catégories"))
SANS_FILTRE = dict(FILTRES)

# Separateur entre le libelle et son compte, dans les menus.
MARQUE_COMPTE = "  ("

# Lignes dessinees d'un coup dans la liste de gauche. Quatre cent quarante
# setups font plusieurs milliers de widgets ; on les donne par paquets, comme
# l'historique des courses et le calendrier.
PAR_BLOC = 40

# Largeur du contenu en dessous de laquelle on ne montre qu'un panneau.
SEUIL_EMPILEMENT = 780

LARGEUR_LISTE = 264

# Decalage des setups sous l'en-tete de leur groupe.
RETRAIT_GROUPE = 14

# Largeurs souhaitees dans le panneau de droite, rognees quand la fenetre
# ne les offre pas : un tableau qui deborde sort de la fenetre sans le
# moindre avertissement, et CTkScrollableFrame ne le retient pas.
LARGEUR_LIBELLE = 208
LARGEUR_LIBELLE_MIN = 108
LARGEUR_VALEUR = 108
LARGEUR_VALEUR_SEULE = 240
LARGEUR_VALEUR_MIN = 62
LARGEUR_COMPARAISON = 132

# Marge interne du panneau : rembourrages plus ascenseur.
MARGE_DETAIL = 58
ECART_PANNEAUX = 10
LARGEUR_REPLI_MIN = 200


class SetupsPage(Page):
    name = "setups"
    title = "Setups"
    subtitle = "Tes réglages par circuit et par voiture, sans lancer le jeu"
    order = 18

    def build(self):
        self.collection = None
        self.filtres = []
        self.entrees = []
        self.ouverts = set()
        self.affiches = 0
        self.choisi = None
        self.epingle = None
        self.lignes = {}
        self._charge = False
        self._empile = None
        self._vue_liste = True

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._construire_entete()
        self._construire_corps()

        # Une disposition par defaut, le temps que Tk annonce la largeur reelle.
        self._disposer(1)
        responsive.suivre_paliers(self, (SEUIL_EMPILEMENT,), self._disposer)

    # --- construction ---

    def _construire_entete(self):
        tete = ctk.CTkFrame(self, fg_color="transparent")
        tete.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        tete.grid_columnconfigure(0, weight=1)

        self.entete = self.header(tete, self.title, self.subtitle)
        self.entete.grid(row=0, column=0, sticky="w")

        self.bouton = ctk.CTkButton(tete, text="Actualiser", width=110, height=32,
                                    font=self.f["body"], corner_radius=8,
                                    fg_color=theme.ACCENT, hover_color=theme.ACCENT_HI,
                                    command=self.refresh)
        self.bouton.grid(row=0, column=1, sticky="e")

    def _construire_corps(self):
        self.corps = ctk.CTkFrame(self, fg_color="transparent")
        self.corps.grid(row=1, column=0, sticky="nsew")

        self._construire_liste()
        self._construire_detail()

    def _construire_liste(self):
        self.panneau_liste = Card(self.corps)
        self.panneau_liste.grid_columnconfigure(0, weight=1)
        self.panneau_liste.grid_rowconfigure(2, weight=1)

        filtres = ctk.CTkFrame(self.panneau_liste, fg_color="transparent")
        filtres.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        filtres.grid_columnconfigure(0, weight=1)

        self.menus = {}
        for rang, (critere, defaut) in enumerate(FILTRES):
            menu = self._menu(filtres, defaut)
            menu.grid(row=rang, column=0, sticky="ew", pady=(0, 6))
            self.menus[critere] = menu

        self.recherche = ctk.CTkEntry(
            filtres, placeholder_text="Rechercher…", height=30, corner_radius=8,
            font=self.f["small"], fg_color=theme.BG, border_color=theme.BORDER)
        self.recherche.grid(row=len(FILTRES), column=0, sticky="ew")
        self.recherche.bind("<KeyRelease>", lambda _: self.appliquer())

        self.compteur = ctk.CTkLabel(self.panneau_liste, text="", font=self.f["tiny"],
                                     text_color=theme.TEXT_FAINT, anchor="w")
        self.compteur.grid(row=1, column=0, sticky="ew", padx=14, pady=(4, 4))

        self.liste = ctk.CTkScrollableFrame(self.panneau_liste, fg_color="transparent")
        self.liste.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 6))
        self.liste.grid_columnconfigure(0, weight=1)
        self._maj_ascenseur = responsive.ascenseur_discret(self.liste, theme.SURFACE)

        self.plus = ctk.CTkButton(self.panneau_liste, text="", height=28,
                                  corner_radius=6, font=self.f["tiny"],
                                  fg_color=theme.SURFACE_HI, hover_color=theme.BORDER,
                                  text_color=theme.TEXT_DIM, command=self.afficher_plus)

    def _menu(self, parent, defaut):
        menu = ctk.CTkOptionMenu(
            parent, values=[defaut], height=30, corner_radius=8,
            font=self.f["small"], dynamic_resizing=False,
            fg_color=theme.SURFACE_HI, button_color=theme.BORDER,
            button_hover_color=theme.TEXT_FAINT, text_color=theme.TEXT,
            dropdown_fg_color=theme.SURFACE_HI, dropdown_text_color=theme.TEXT,
            dropdown_hover_color=theme.ACCENT, dropdown_font=self.f["small"],
            command=lambda _=None: self.appliquer())
        menu.set(defaut)
        return menu

    def _construire_detail(self):
        self.panneau_detail = Card(self.corps)
        self.panneau_detail.grid_columnconfigure(0, weight=1)
        self.panneau_detail.grid_rowconfigure(1, weight=1)

        self.tete_detail = ctk.CTkFrame(self.panneau_detail, fg_color="transparent")
        self.tete_detail.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))
        self.tete_detail.grid_columnconfigure(0, weight=1)

        self.detail = ctk.CTkScrollableFrame(self.panneau_detail,
                                             fg_color="transparent")
        self.detail.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 10))
        self.detail.grid_columnconfigure(0, weight=1)
        self._maj_ascenseur_detail = responsive.ascenseur_discret(self.detail,
                                                                  theme.SURFACE)
        # Les colonnes se calculent sur la largeur reelle du panneau : il
        # faut donc redessiner quand elle change franchement.
        responsive.suivre_largeur(self, lambda _=None: self._peindre_detail(),
                                  marge=36)

    # --- disposition ---

    def _disposer(self, palier):
        """Cote a cote quand il y a la place, l'un ou l'autre sinon.

        Empiler les deux panneaux serait tentant, mais a cette largeur la
        fenetre est aussi courte : la liste et le tableau se partageraient
        deux cents pixels chacun, et aucun des deux ne se lirait. On montre
        donc la liste, puis le setup choisi, avec un retour.
        """
        empile = palier == 0
        if empile == self._empile:
            return
        self._empile = empile

        for colonne in (0, 1):
            self.corps.grid_columnconfigure(colonne, weight=0, minsize=0)
        self.corps.grid_rowconfigure(0, weight=1)
        self.corps.grid_columnconfigure(0, weight=1 if empile else 0,
                                        minsize=0 if empile else LARGEUR_LISTE)
        if not empile:
            self.corps.grid_columnconfigure(1, weight=1)

        self._montrer_panneau()
        self._peindre_detail()

    def _montrer_panneau(self):
        """Place les panneaux selon la largeur, et le retour en mode etroit."""
        self.panneau_liste.grid_forget()
        self.panneau_detail.grid_forget()
        if not self._empile:
            self.panneau_liste.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
            self.panneau_detail.grid(row=0, column=1, sticky="nsew")
        elif self._vue_liste or self.choisi is None:
            self.panneau_liste.grid(row=0, column=0, sticky="nsew")
        else:
            self.panneau_detail.grid(row=0, column=0, sticky="nsew")

    def revenir_a_la_liste(self):
        self._vue_liste = True
        self._montrer_panneau()

    # --- chargement ---

    def on_show(self):
        if not self._charge:
            self._charge = True
            self.refresh()

    def refresh(self):
        self.bouton.configure(state="disabled", text="…")
        self.app.set_status("Lecture des setups…")
        self.app.run_async(st.charger, self._recu, self._echec)

    def _recu(self, collection):
        self.bouton.configure(state="normal", text="Actualiser")
        self.collection = collection
        self.choisi = self.epingle = None
        self._reinitialiser_menus()
        self.ouverts = set()
        self.appliquer()
        self.app.set_status(
            f"{len(collection)} setups lus dans {collection.dossier}"
            if len(collection) else f"Aucun setup dans {collection.dossier}")

    def _echec(self, exc):
        self.bouton.configure(state="normal", text="Actualiser")
        self.collection = None
        self.filtres = []
        self.choisi = self.epingle = None
        self._vider(self.liste, "")
        self._peindre_detail()
        message = str(exc) if isinstance(exc, HubError) else f"Lecture impossible.\n{exc}"
        self._vider(self.detail, message)
        self.app.set_status("Setups illisibles", error=True)

    def _reinitialiser_menus(self):
        for critere, defaut in FILTRES:
            self.menus[critere].set(defaut)

    def _choix(self, critere):
        """La valeur retenue pour ce critere, ou None si le filtre est ouvert."""
        choix = self.menus[critere].get()
        if choix == SANS_FILTRE[critere]:
            return None
        return choix.rsplit(MARQUE_COMPTE, 1)[0]

    def _synchroniser_menus(self):
        """Chaque menu ne propose que ce qui reste atteignable.

        Un menu qui listerait tout finirait par offrir des combinaisons vides —
        la Genesis a Sebring alors qu'on a deja choisi la categorie LMGT3. On
        recalcule donc les valeurs de chaque menu a partir des *autres* filtres,
        son propre choix mis de cote.
        """
        for critere, defaut in FILTRES:
            autres = {c: self._choix(c) for c, _ in FILTRES if c != critere}
            parmi = self.collection.filtrer(recherche=self.recherche.get(), **autres)
            valeurs = self.collection.valeurs(critere, parmi)
            self.menus[critere].configure(
                values=[defaut] + [f"{nom}{MARQUE_COMPTE}{n})" for nom, n in valeurs])

    # --- liste ---

    def appliquer(self, garder=0):
        """Refait la liste. `garder` rouvre autant de lignes qu'avant.

        Sans lui, deplier un groupe replacerait la liste a son debut : on
        perdrait de vue le groupe que l'on vient justement d'ouvrir.
        """
        if self.collection is None:
            return
        self._synchroniser_menus()
        self.filtres = self.collection.filtrer(
            circuit=self._choix("circuit"), voiture=self._choix("voiture"),
            categorie=self._choix("categorie"), recherche=self.recherche.get())
        self.entrees = self._entrees()
        self.lignes = {}
        self.affiches = 0
        for enfant in self.liste.winfo_children():
            enfant.destroy()

        if not self.entrees:
            self.plus.grid_forget()
            self._vider(self.liste,
                        "Aucun setup ne correspond." if len(self.collection)
                        else "Aucun setup enregistré pour l'instant.")
            self._maj_ascenseur()
        else:
            while True:
                self._afficher_bloc()
                if self.affiches >= min(garder, len(self.entrees)):
                    break
        self._maj_compteur()

    def groupe_par(self):
        """Par quoi regrouper la liste, ou None pour un affichage a plat."""
        circuit, voiture = self._choix("circuit"), self._choix("voiture")
        if circuit and not voiture:
            return "voiture"
        if voiture and not circuit:
            return "circuit"
        return None

    def _entrees(self):
        """Les lignes a dessiner : des setups, ou des en-tetes et des setups."""
        critere = self.groupe_par()
        if critere is None:
            return [(None, setup) for setup in self.filtres]

        lire = st.CRITERES[critere]
        groupes = {}
        for setup in self.filtres:
            groupes.setdefault(lire(setup), []).append(setup)

        # Un seul groupe n'a rien a plier : le replier ferait un clic de plus
        # pour rien.
        if len(groupes) == 1:
            self.ouverts |= set(groupes)

        entrees = []
        for nom in sorted(groupes, key=lambda n: st._sans_accents(n).lower()):
            entrees.append((nom, len(groupes[nom])))
            if nom in self.ouverts:
                entrees.extend((None, setup) for setup in groupes[nom])
        return entrees

    def basculer(self, nom):
        """Ouvre ou ferme un groupe, sans faire remonter la liste."""
        self.ouverts.symmetric_difference_update({nom})
        self.appliquer(garder=self.affiches)

    def afficher_plus(self):
        self._afficher_bloc()
        self._maj_compteur()

    def _afficher_bloc(self):
        groupe_par = self.groupe_par()
        bloc = self.entrees[self.affiches:self.affiches + PAR_BLOC]
        for decalage, (groupe, valeur) in enumerate(bloc):
            rang = self.affiches + decalage
            if groupe is None:
                self._ligne(rang, valeur, sous_groupe=groupe_par is not None)
            else:
                self._ligne_groupe(rang, groupe, valeur)
        self.affiches += len(bloc)

        reste = len(self.entrees) - self.affiches
        if reste > 0:
            self.plus.configure(text=f"Afficher {min(reste, PAR_BLOC)} de plus"
                                     f"  ({reste} restants)")
            self.plus.grid(row=3, column=0, sticky="ew", padx=6, pady=(0, 8))
        else:
            self.plus.grid_forget()
        self._maj_ascenseur()

    def _ligne_groupe(self, rang, nom, total):
        ouvert = nom in self.ouverts
        ligne = ctk.CTkFrame(self.liste, fg_color=theme.SURFACE_HI, corner_radius=6)
        ligne.grid(row=rang, column=0, sticky="ew", pady=(6, 1))
        ligne.grid_columnconfigure(1, weight=1)

        chevron = ctk.CTkLabel(ligne, text="▾" if ouvert else "▸",
                               font=self.f["tiny"], text_color=theme.TEXT_DIM,
                               width=14)
        chevron.grid(row=0, column=0, sticky="w", padx=(8, 0), pady=6)

        titre = ctk.CTkLabel(ligne, text=tronquer(nom, LARGEUR_LISTE - 66),
                             font=self.f["heading"], text_color=theme.TEXT,
                             anchor="w")
        titre.grid(row=0, column=1, sticky="ew", padx=(4, 4))

        compte = ctk.CTkLabel(ligne, text=str(total), font=self.f["tiny"],
                              text_color=theme.TEXT_FAINT, anchor="e")
        compte.grid(row=0, column=2, sticky="e", padx=(4, 10))

        for cible in (ligne, chevron, titre, compte):
            cible.bind("<Button-1>", lambda _=None, n=nom: self.basculer(n))

    def _ligne(self, rang, setup, sous_groupe=False):
        """Une ligne de setup. Decalee, et resumee autrement, sous un groupe.

        Repeter « Ferrari 499P · Le Mans » sous l'en-tete « Ferrari 499P »,
        alors que le circuit est deja filtre, ne dit rien : la date, elle,
        distingue deux versions d'un meme reglage.
        """
        retrait = RETRAIT_GROUPE if sous_groupe else 0
        largeur = LARGEUR_LISTE - 26 - retrait
        ligne = ctk.CTkFrame(self.liste, fg_color="transparent", corner_radius=6)
        ligne.grid(row=rang, column=0, sticky="ew", padx=(retrait, 0), pady=1)
        ligne.grid_columnconfigure(0, weight=1)

        titre = ctk.CTkLabel(ligne, text=tronquer(setup.nom, largeur),
                             font=self.f["small"], text_color=theme.TEXT, anchor="w")
        titre.grid(row=0, column=0, sticky="ew", padx=10, pady=(5, 0))

        if sous_groupe:
            morceaux = [f"{setup.modifie:%d/%m/%Y}"]
        else:
            morceaux = [setup.voiture, setup.circuit]
        if setup.sous_la_pluie:
            morceaux.append("pluie")
        sous_titre = ctk.CTkLabel(ligne, text=tronquer(" · ".join(morceaux), largeur),
                                  font=self.f["tiny"], text_color=theme.TEXT_FAINT,
                                  anchor="w")
        sous_titre.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))

        # Le clic atterrit sur l'etiquette survolee, pas sur le cadre qui la
        # porte : chaque enfant doit donc ecouter, sinon la moitie de la ligne
        # est morte.
        for cible in (ligne, titre, sous_titre):
            cible.bind("<Button-1>", lambda _=None, s=setup: self.selectionner(s))
            cible.bind("<Enter>", lambda _=None, l=ligne: self._survol(l, True))
            cible.bind("<Leave>", lambda _=None, l=ligne: self._survol(l, False))

        self.lignes[setup.chemin] = (ligne, titre, sous_titre)
        self._teinter(setup, ligne, titre, sous_titre)

    def _survol(self, ligne, dedans):
        if ligne.winfo_exists() and ligne.cget("fg_color") != theme.ACCENT:
            ligne.configure(fg_color=theme.SURFACE_HI if dedans else "transparent")

    def _teinter(self, setup, ligne, titre, sous_titre):
        """Fond et texte de la ligne, selon qu'elle est ouverte ou epinglee.

        Le rouge d'accent avale le gris des sous-titres : sur fond selectionne,
        les deux etiquettes passent en clair.
        """
        choisi = self.choisi is not None and setup.chemin == self.choisi.chemin
        epingle = self.epingle is not None and setup.chemin == self.epingle.chemin
        if choisi:
            ligne.configure(fg_color=theme.ACCENT)
            titre.configure(text_color=theme.TEXT)
            sous_titre.configure(text_color=theme.TEXT)
        else:
            ligne.configure(fg_color=theme.SURFACE_HI if epingle else "transparent")
            titre.configure(text_color=theme.TEXT)
            sous_titre.configure(text_color=theme.TEXT_FAINT)

    def _rafraichir_teintes(self):
        for groupe, valeur in self.entrees[:self.affiches]:
            if groupe is not None:
                continue
            trio = self.lignes.get(valeur.chemin)
            if trio is not None and trio[0].winfo_exists():
                self._teinter(valeur, *trio)

    ETIQUETTES_GROUPE = {"voiture": ("voiture", "voitures"),
                         "circuit": ("circuit", "circuits")}

    def _maj_compteur(self):
        if self.collection is None:
            return
        total = len(self.collection)
        texte = (f"{total} setups" if len(self.filtres) == total
                 else f"{len(self.filtres)} sur {total} setups")
        critere = self.groupe_par()
        if critere is not None:
            groupes = sum(1 for nom, _ in self.entrees if nom is not None)
            singulier, pluriel = self.ETIQUETTES_GROUPE[critere]
            texte += f" · {groupes} {singulier if groupes == 1 else pluriel}"
        self.compteur.configure(text=texte)

    # --- selection ---

    def selectionner(self, setup):
        self.choisi = setup
        self._vue_liste = False
        self._rafraichir_teintes()
        self._montrer_panneau()
        self._peindre_detail()

    def epingler(self):
        """Retient le setup courant comme terme de comparaison."""
        self.epingle = None if self.epingle is not None else self.choisi
        self._rafraichir_teintes()
        self._peindre_detail()

    def copier(self):
        texte = (st.exporter(self.choisi) if self.epingle is None
                 else self._comparaison_en_texte())
        self.clipboard_clear()
        self.clipboard_append(texte)
        self.app.set_status("Copié dans le presse-papiers")

    def voir_dans_le_dossier(self):
        """Ouvre l'Explorateur sur le fichier du setup choisi, deja selectionne.

        Le setup choisi, y compris en comparaison : c'est celui que la liste
        met en evidence, et la barre d'etat dit lequel on a ouvert.
        """
        setup = self.choisi
        try:
            explorateur.montrer(setup.chemin)
        except HubError as exc:
            # La barre d'etat tient sur une ligne ; l'erreur en a deux.
            message = " ".join(ligne.strip() for ligne in str(exc).splitlines())
            self.app.set_status(message, error=True)
            return
        self.app.set_status(f"Dossier ouvert sur {setup.chemin.name}")

    # --- panneau de droite ---

    def _peindre_detail(self):
        for enfant in self.tete_detail.winfo_children():
            enfant.destroy()
        for enfant in self.detail.winfo_children():
            enfant.destroy()

        if self.choisi is None:
            self._peindre_accueil()
        elif self.epingle is not None and self.epingle.chemin != self.choisi.chemin:
            self._peindre_comparaison()
        else:
            self._peindre_setup()
        self._maj_ascenseur_detail()

    def _peindre_accueil(self):
        """Ce qu'on voit avant d'avoir choisi : l'etat de la collection."""
        ctk.CTkLabel(self.tete_detail, text="Ta collection", font=self.f["title"],
                     text_color=theme.TEXT, anchor="w").grid(row=0, column=0,
                                                             sticky="ew")
        if self.collection is None:
            self._vider(self.detail, "Lecture des setups…")
            return

        resume = (f"{len(self.collection)} setups · "
                  f"{len(self.collection.circuits())} circuits · "
                  f"{len(self.collection.voitures())} voitures")
        note = ctk.CTkLabel(self.tete_detail, text=resume, font=self.f["small"],
                            text_color=theme.TEXT_DIM, anchor="w")
        note.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        if not len(self.collection):
            self._vider(self.detail,
                        f"Aucun fichier .svm dans {self.collection.dossier}.\n"
                        "Le jeu y range un dossier par circuit dès que tu "
                        "enregistres un réglage.")
            return

        par_voiture = {}
        for setup in self.collection.setups:
            par_voiture.setdefault(setup.voiture, []).append(setup)

        rang = 0
        for voiture in sorted(par_voiture, key=lambda n: st._sans_accents(n).lower()):
            setups = par_voiture[voiture]
            circuits = {}
            for setup in setups:
                circuits[setup.circuit] = circuits.get(setup.circuit, 0) + 1
            rang = self._ligne_recap(rang, voiture, len(setups), circuits)

        pied = ctk.CTkLabel(
            self.detail,
            text="Choisis un setup à gauche pour en voir les valeurs.",
            font=self.f["small"], text_color=theme.TEXT_FAINT, anchor="w")
        pied.grid(row=rang, column=0, sticky="ew", padx=12, pady=(14, 6))

    def _ligne_recap(self, rang, voiture, total, circuits):
        ctk.CTkLabel(self.detail, text=f"{voiture}  ({total})",
                     font=self.f["heading"], text_color=theme.TEXT,
                     anchor="w").grid(row=rang, column=0, sticky="ew",
                                      padx=12, pady=(10, 0))
        detail = " · ".join(
            f"{nom} {n}" for nom, n in
            sorted(circuits.items(), key=lambda kv: st._sans_accents(kv[0]).lower()))
        ligne = ctk.CTkLabel(self.detail, text=detail, font=self.f["tiny"],
                             text_color=theme.TEXT_DIM, anchor="w", justify="left")
        ligne.grid(row=rang + 1, column=0, sticky="ew", padx=12, pady=(1, 0))
        self._replier(ligne)
        return rang + 2

    # --- un setup ---

    def _peindre_setup(self):
        setup = self.choisi
        self._entete_setup(setup)

        rang = 0
        for titre, colonnes, lignes in setup.groupes():
            rang = self._bloc(rang, titre, colonnes, lignes)
        if rang == 0:
            self._vider(self.detail, "Ce fichier ne contient aucun réglage lisible.")

    def _entete_setup(self, setup):
        ctk.CTkLabel(self.tete_detail,
                     text=tronquer(setup.nom, self._largeur_detail()),
                     font=self.f["title"],
                     text_color=theme.TEXT, anchor="w").grid(row=0, column=0,
                                                             sticky="ew")
        morceaux = [setup.voiture, setup.circuit]
        if setup.categorie:
            morceaux.append(setup.categorie)
        if setup.saison:
            morceaux.append(setup.saison)
        morceaux.append(f"modifié le {setup.modifie:%d/%m/%Y}")
        sous = ctk.CTkLabel(self.tete_detail, text=" · ".join(morceaux),
                            font=self.f["small"], text_color=theme.TEXT_DIM,
                            anchor="w", justify="left")
        sous.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self._replier(sous)

        if setup.notes:
            notes = ctk.CTkLabel(self.tete_detail,
                                 text=setup.notes.replace("\n", " · "),
                                 font=self.f["tiny"], text_color=theme.TEXT_FAINT,
                                 anchor="w", justify="left")
            notes.grid(row=2, column=0, sticky="ew", pady=(4, 0))
            self._replier(notes)

        self._boutons_detail(rang=3)

    def _boutons_detail(self, rang):
        barre = ctk.CTkFrame(self.tete_detail, fg_color="transparent")
        barre.grid(row=rang, column=0, sticky="ew", pady=(10, 0))

        colonne = 0
        if self._empile:
            ctk.CTkButton(barre, text="← Liste", width=76, height=28,
                          corner_radius=8, font=self.f["small"],
                          fg_color=theme.SURFACE_HI, hover_color=theme.BORDER,
                          text_color=theme.TEXT,
                          command=self.revenir_a_la_liste).grid(row=0, column=0,
                                                                padx=(0, 8))
            colonne = 1

        epingle = self.epingle is not None
        ctk.CTkButton(barre,
                      text="Ne plus comparer" if epingle else "Comparer avec…",
                      width=140, height=28, corner_radius=8, font=self.f["small"],
                      fg_color=theme.SURFACE_HI if epingle else theme.ACCENT,
                      hover_color=theme.BORDER if epingle else theme.ACCENT_HI,
                      text_color=theme.TEXT,
                      command=self.epingler).grid(row=0, column=colonne)
        ctk.CTkButton(barre, text="Voir dans le dossier", width=148, height=28,
                      corner_radius=8, font=self.f["small"],
                      fg_color=theme.SURFACE_HI, hover_color=theme.BORDER,
                      text_color=theme.TEXT,
                      command=self.voir_dans_le_dossier).grid(
            row=0, column=colonne + 1, padx=(8, 0))
        ctk.CTkButton(barre, text="Copier", width=84, height=28, corner_radius=8,
                      font=self.f["small"], fg_color=theme.SURFACE_HI,
                      hover_color=theme.BORDER, text_color=theme.TEXT,
                      command=self.copier).grid(row=0, column=colonne + 2,
                                                padx=(8, 0))

        if epingle:
            # Sous les boutons et non a leur suite : a quatre boutons la ligne
            # n'a plus la place d'un nom entier, meme a la taille par defaut, et
            # une note qui deborde pousse tout le panneau hors de la fenetre.
            note = ctk.CTkLabel(
                barre, text="épinglé : " + self.epingle.nom,
                font=self.f["tiny"], text_color=theme.ACCENT, anchor="w",
                justify="left")
            note.grid(row=1, column=0, columnspan=colonne + 3, sticky="ew",
                      pady=(6, 0))
            self._replier(note)

    def _largeur_detail(self):
        """Place offerte au panneau de droite, mesuree sur la page.

        Surtout pas sur le panneau lui-meme : sa largeur depend de ce qu'on y
        met, et la mesure se mordrait la queue — le contenu resterait large et
        pousserait le panneau hors de la fenetre au lieu de se replier.
        """
        dispo = self.winfo_width() - MARGE_DETAIL
        if not self._empile:
            dispo -= LARGEUR_LISTE + ECART_PANNEAUX
        return dispo

    def _replier(self, label):
        """Fait passer un texte a la ligne dans la largeur offerte.

        On regle `wraplength` au moment ou l'on dessine, sans s'abonner aux
        redimensionnements : `_peindre_detail` est deja rappele a chaque
        changement de largeur, et un abonnement par etiquette s'accumulerait
        a chaque repeinture.
        """
        label.configure(wraplength=max(LARGEUR_REPLI_MIN, self._largeur_detail()))

    def _largeurs(self, colonnes, souhaitee):
        """Repartit la place disponible entre le libelle et les valeurs.

        On rogne le libelle en premier — un intitule tronque se devine, une
        valeur tronquee ne se devine pas — puis les valeurs si besoin.
        """
        nombre = len(colonnes) or 1
        libelle, valeur = LARGEUR_LIBELLE, souhaitee
        dispo = self._largeur_detail()
        if dispo < LARGEUR_LIBELLE_MIN + nombre * LARGEUR_VALEUR_MIN:
            return libelle, valeur  # fenetre pas encore dessinee
        if libelle + nombre * valeur > dispo:
            libelle = max(LARGEUR_LIBELLE_MIN, dispo - nombre * valeur)
            if libelle + nombre * valeur > dispo:
                valeur = max(LARGEUR_VALEUR_MIN, (dispo - libelle) // nombre)
        return libelle, valeur

    def _bloc(self, rang, titre, colonnes, lignes):
        ctk.CTkLabel(self.detail, text=titre.upper(), font=self.f["heading"],
                     text_color=theme.TEXT_FAINT, anchor="w").grid(
            row=rang, column=0, sticky="ew", padx=12, pady=(14, 4))
        rang += 1

        tableau = ctk.CTkFrame(self.detail, fg_color="transparent")
        tableau.grid(row=rang, column=0, sticky="ew", padx=12)
        # Une valeur seule a toute la place ; quatre roues se la partagent.
        souhaitee = LARGEUR_VALEUR if colonnes else LARGEUR_VALEUR_SEULE
        intitule, largeur = self._largeurs(colonnes, souhaitee)
        nombre = len(colonnes) or 1
        tableau.grid_columnconfigure(0, minsize=intitule)
        for index in range(nombre):
            tableau.grid_columnconfigure(index + 1, minsize=largeur)
        # Le surplus va a une colonne vide en bout de ligne : donne au libelle,
        # il eloignerait la valeur de son intitule de plusieurs centimetres.
        tableau.grid_columnconfigure(nombre + 1, weight=1)

        interne = 0
        if colonnes:
            for index, nom in enumerate(colonnes):
                ctk.CTkLabel(tableau, text=nom, font=self.f["tiny"],
                             text_color=theme.TEXT_FAINT, anchor="w").grid(
                    row=0, column=index + 1, sticky="ew", padx=(8, 0))
            interne = 1

        for ligne in lignes:
            ctk.CTkLabel(tableau, text=tronquer(ligne.libelle, intitule),
                         font=self.f["small"], text_color=theme.TEXT_DIM,
                         anchor="w").grid(row=interne, column=0, sticky="ew",
                                          pady=2)
            for index, valeur in enumerate(ligne.valeurs):
                ctk.CTkLabel(tableau, text=tronquer(valeur or st.ABSENT, largeur),
                             font=self.f["small"], text_color=theme.TEXT,
                             anchor="w").grid(row=interne, column=index + 1,
                                              sticky="ew", padx=(8, 0), pady=2)
            interne += 1
        return rang + 1

    # --- comparaison ---

    def _peindre_comparaison(self):
        gauche, droite = self.epingle, self.choisi
        blocs = st.comparer(gauche, droite)
        total, differents = st.resumer(blocs)

        ctk.CTkLabel(self.tete_detail, text="Comparaison", font=self.f["title"],
                     text_color=theme.TEXT, anchor="w").grid(row=0, column=0,
                                                             sticky="ew")
        # Chaque nom prend la couleur de sa colonne : sans cela, rien ne dit
        # laquelle des deux valeurs appartient a quel setup.
        noms = ctk.CTkFrame(self.tete_detail, fg_color="transparent")
        noms.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        noms.grid_columnconfigure(0, weight=1)
        for rang, (setup, couleur, cote) in enumerate(
                ((gauche, theme.TEXT, "gauche"), (droite, theme.ACCENT, "droite"))):
            etiquette = ctk.CTkLabel(noms, text=f"colonne de {cote} · {setup.nom}",
                                     font=self.f["small"], text_color=couleur,
                                     anchor="w", justify="left")
            etiquette.grid(row=rang, column=0, sticky="ew")
            self._replier(etiquette)

        resume = ctk.CTkLabel(
            self.tete_detail,
            text=f"{differents} différence(s) sur {total} réglages comparés",
            font=self.f["tiny"], text_color=theme.TEXT_DIM, anchor="w")
        resume.grid(row=2, column=0, sticky="ew", pady=(4, 0))

        if gauche.voiture != droite.voiture:
            avertir = ctk.CTkLabel(
                self.tete_detail,
                text="Voitures différentes : beaucoup d'écarts n'auront pas de sens.",
                font=self.f["tiny"], text_color=theme.WARN, anchor="w",
                justify="left")
            avertir.grid(row=3, column=0, sticky="ew", pady=(4, 0))
            self._replier(avertir)

        self._boutons_detail(rang=4)

        rang = 0
        for titre, ecarts in blocs:
            chauds = [e for e in ecarts if e.different]
            if not chauds:
                continue
            rang = self._bloc_ecarts(rang, titre, chauds)

        if rang == 0:
            self._vider(self.detail, "Les deux setups sont identiques.")

    def _bloc_ecarts(self, rang, titre, ecarts):
        ctk.CTkLabel(self.detail, text=titre.upper(), font=self.f["heading"],
                     text_color=theme.TEXT_FAINT, anchor="w").grid(
            row=rang, column=0, sticky="ew", padx=12, pady=(14, 4))
        rang += 1

        tableau = ctk.CTkFrame(self.detail, fg_color="transparent")
        tableau.grid(row=rang, column=0, sticky="ew", padx=12)
        intitule, largeur = self._largeurs((0, 0), LARGEUR_COMPARAISON)
        tableau.grid_columnconfigure(0, minsize=intitule)
        tableau.grid_columnconfigure(1, minsize=largeur)
        tableau.grid_columnconfigure(2, minsize=largeur)
        tableau.grid_columnconfigure(3, weight=1)

        for index, ecart in enumerate(ecarts):
            ctk.CTkLabel(tableau, text=tronquer(ecart.libelle, intitule),
                         font=self.f["small"], text_color=theme.TEXT_DIM,
                         anchor="w").grid(row=index, column=0, sticky="ew",
                                          pady=2)
            for colonne, valeur in ((1, ecart.gauche), (2, ecart.droite)):
                ctk.CTkLabel(tableau,
                             text=tronquer(valeur, largeur),
                             font=self.f["small"],
                             text_color=theme.ACCENT if colonne == 2 else theme.TEXT,
                             anchor="w").grid(row=index, column=colonne,
                                              sticky="ew", padx=(8, 0), pady=2)
        return rang + 1

    def _comparaison_en_texte(self):
        gauche, droite = self.epingle, self.choisi
        blocs = st.comparer(gauche, droite)
        total, differents = st.resumer(blocs)
        lignes = [f"{gauche.nom}", f"{droite.nom}",
                  f"{differents} différence(s) sur {total} réglages comparés"]
        for titre, ecarts in blocs:
            chauds = [e for e in ecarts if e.different]
            if not chauds:
                continue
            lignes.append("")
            lignes.append(titre.upper())
            for ecart in chauds:
                lignes.append(f"  {ecart.libelle:<34}{ecart.gauche:<20}"
                              f"→ {ecart.droite}")
        # Meme fin de ligne que `exporter` : le presse-papiers finit
        # souvent dans un editeur Windows, qui attend du CRLF.
        return os.linesep.join(lignes)

    # --- utilitaire ---

    def _vider(self, cadre, message):
        for enfant in cadre.winfo_children():
            enfant.destroy()
        if not message:
            return
        etiquette = ctk.CTkLabel(cadre, text=message, font=self.f["small"],
                                 text_color=theme.TEXT_FAINT, anchor="w",
                                 justify="left")
        etiquette.grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        responsive.replier_texte(etiquette, self, marge=90)
