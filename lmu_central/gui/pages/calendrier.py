"""Page Calendrier : les epreuves a venir, et les amis inscrits dessus.

Deux blocs. En haut, ou sont tes amis — c'est la question qu'on se pose en
premier. En dessous, le calendrier complet avec ses filtres.
"""

import customtkinter as ctk

from ...core import calendrier as cal
from ...core.timefmt import local_time
from .. import responsive, theme
from ..widgets import Card, tronquer
from .base import Page

TOUS = "Tout"
AVEC_AMIS = "Avec des amis"
NIVEAUX_FILTRES = ("beginner", "intermediate", "advanced",
                   "weekly", "special", "championship")

# cle, intitule, largeur, extensible, priorite (0 = ne part jamais)
COLONNES = (
    ("quand",    "QUAND",      96, 0, 0),
    ("nom",      "ÉPREUVE",   170, 1, 0),
    ("circuit",  "CIRCUIT",   150, 1, 2),
    ("niveau",   "NIVEAU",    104, 0, 4),
    ("inscrits", "INSCRITS",   88, 0, 3),
    ("amis",     "AMIS",      140, 1, 0),
)
ESPACE = 8
MARGE = 54

# Lignes dessinees d'un coup. Deux jours de daily font plus de 400 epreuves,
# soit des milliers de widgets : Tk met alors une seconde a repeindre, pour un
# tableau que personne ne lit jusqu'au bout.
PAR_BLOC = 25

# En dessous de ce delai, le depart est imminent : on le signale en couleur.
IMMINENT_MIN = 30


class CalendrierPage(Page):
    name = "calendrier"
    title = "Calendrier"
    subtitle = "Les épreuves à venir, et les amis inscrits dessus"
    order = 15

    def build(self):
        self.epreuves = []
        self.visibles = list(COLONNES)
        self.largeurs = {c[0]: c[2] for c in COLONNES}
        self._charge = False
        self._calendrier = None
        self.affichees = 0
        self.filtrees = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._construire_entete()
        self._construire_amis()
        self._construire_tableau()

        responsive.suivre_largeur(self, self._ajuster_colonnes)

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

    def _construire_amis(self):
        self.carte_amis = Card(self)
        self.carte_amis.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.carte_amis.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.carte_amis, text="TES AMIS", font=self.f["heading"],
                     text_color=theme.TEXT_FAINT, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=16, pady=(12, 6))

        self.liste_amis = ctk.CTkFrame(self.carte_amis, fg_color="transparent")
        self.liste_amis.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))
        self.liste_amis.grid_columnconfigure(0, weight=1)
        self.note_amis = None
        self._note_amis("Chargement…")

    def _construire_tableau(self):
        barre = ctk.CTkFrame(self, fg_color="transparent")
        barre.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        barre.grid_columnconfigure(1, weight=1)

        valeurs = [TOUS] + [cal.LIBELLES_NIVEAU[n] for n in NIVEAUX_FILTRES] + [AVEC_AMIS]
        self.filtre = ctk.CTkSegmentedButton(
            barre, values=valeurs, font=self.f["small"], height=30, corner_radius=8,
            command=lambda _=None: self.appliquer(),
            selected_color=theme.ACCENT, selected_hover_color=theme.ACCENT_HI,
            unselected_color=theme.SURFACE_HI, unselected_hover_color=theme.BORDER,
            text_color=theme.TEXT)
        self.filtre.grid(row=0, column=0, sticky="w")
        self.filtre.set(TOUS)

        self.compteur = ctk.CTkLabel(barre, text="", font=self.f["tiny"],
                                     text_color=theme.TEXT_FAINT, anchor="e")
        self.compteur.grid(row=0, column=1, sticky="e", padx=(12, 0))

        carte = Card(self)
        carte.grid(row=3, column=0, sticky="nsew")
        carte.grid_columnconfigure(0, weight=1)
        carte.grid_rowconfigure(1, weight=1)

        self.entetes = ctk.CTkFrame(carte, fg_color="transparent")
        self.entetes.grid(row=0, column=0, sticky="ew", padx=(20, 34), pady=(12, 4))

        self.liste = ctk.CTkScrollableFrame(carte, fg_color="transparent")
        self.liste.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 10))
        self.liste.grid_columnconfigure(0, weight=1)
        self._maj_ascenseur = responsive.ascenseur_discret(self.liste, theme.SURFACE)

        self.plus = ctk.CTkButton(carte, text="", height=30, corner_radius=6,
                                  font=self.f["small"], fg_color=theme.SURFACE_HI,
                                  hover_color=theme.BORDER, text_color=theme.TEXT_DIM,
                                  command=self.afficher_plus)

        self._construire_entetes()

    # --- colonnes adaptatives ---

    def _ajuster_colonnes(self, largeur):
        retenues = list(COLONNES)
        while largeur > 1 and self._largeur_requise(retenues) > largeur:
            sacrifiee = max(retenues, key=lambda c: c[4])
            if sacrifiee[4] == 0:
                break
            retenues.remove(sacrifiee)
        if [c[0] for c in retenues] == [c[0] for c in self.visibles]:
            return
        self.visibles = retenues
        self.largeurs = self._largeurs_effectives(largeur)
        self._construire_entetes()
        self.appliquer()

    def _largeurs_effectives(self, largeur):
        """Repartit la place en trop entre les colonnes extensibles.

        Tk elargit ces colonnes au-dela de leur minsize : tronquer sur la
        largeur declaree gacherait la place gagnee.
        """
        effectives = {c[0]: c[2] for c in self.visibles}
        extensibles = [c[0] for c in self.visibles if c[3]]
        surplus = largeur - self._largeur_requise(self.visibles)
        if extensibles and surplus > 0:
            part = surplus // len(extensibles)
            for cle in extensibles:
                effectives[cle] += part
        return effectives

    @staticmethod
    def _largeur_requise(colonnes):
        return sum(c[2] for c in colonnes) + ESPACE * len(colonnes) + MARGE

    def _configurer_grille(self, grille):
        for colonne in range(len(COLONNES)):
            grille.grid_columnconfigure(colonne, weight=0, minsize=0)
        for colonne, (_, _, largeur, extensible, _) in enumerate(self.visibles):
            grille.grid_columnconfigure(colonne, minsize=largeur, weight=extensible)

    def _construire_entetes(self):
        for enfant in self.entetes.winfo_children():
            enfant.destroy()
        self._configurer_grille(self.entetes)
        for colonne, (_, titre, _, _, _) in enumerate(self.visibles):
            ctk.CTkLabel(self.entetes, text=titre, font=self.f["tiny"],
                         text_color=theme.TEXT_FAINT, anchor="w").grid(
                row=0, column=colonne, sticky="ew", padx=(0, ESPACE))

    # --- chargement ---

    def on_show(self):
        if not self._charge:
            self._charge = True
            self.refresh()

    def refresh(self):
        self.bouton.configure(state="disabled", text="…")
        self.app.set_status("Lecture du calendrier…")
        self.app.run_async(lambda: cal.ouvrir(self.ctx), self._recu, self._echec)

    def _recu(self, calendrier):
        self.bouton.configure(state="normal", text="Actualiser")
        self._calendrier = calendrier
        self.epreuves = calendrier.a_venir()
        self._maj_amis()
        self.appliquer()
        self.app.set_status(
            f"Calendrier du {local_time(calendrier.date)}" if calendrier.hors_ligne
            else "Calendrier à jour")

    def _echec(self, exc):
        self.bouton.configure(state="normal", text="Actualiser")
        self.epreuves = []
        self._calendrier = None
        self._note_amis(
            "Calendrier indisponible — lance Le Mans Ultimate, puis Actualiser.")
        self._vider(f"Calendrier indisponible.\n\n{str(exc).replace(chr(10), ' ')[:200]}")
        self.app.set_status("Calendrier indisponible", error=True)

    # --- bloc des amis ---

    def _note_amis(self, texte):
        """Remplace le contenu du bloc par une seule explication."""
        for enfant in self.liste_amis.winfo_children():
            enfant.destroy()
        self.note_amis = ctk.CTkLabel(self.liste_amis, text=texte,
                                      font=self.f["small"], text_color=theme.TEXT_DIM,
                                      anchor="w", justify="left")
        self.note_amis.grid(row=0, column=0, sticky="ew")
        responsive.replier_texte(self.note_amis, self, marge=70)

    def _maj_amis(self):
        presences = []
        for epreuve in self.epreuves:
            for ami in epreuve.amis:
                presences.append((ami.nom, epreuve))
        presences.sort(key=lambda p: (p[1].debut or "", p[0]))

        if not presences:
            # Hors ligne, l'absence d'amis ne veut rien dire : le backend n'a
            # pas repondu. Le dire, plutot que de laisser croire a un vide.
            if self._calendrier is not None and not self._calendrier.amis_connus:
                self._note_amis(
                    "Inscriptions des amis inconnues : elles demandent une session "
                    "ouverte.\nLance Le Mans Ultimate, puis Actualiser.")
            else:
                self._note_amis(
                    "Aucun ami inscrit ou en course pour le moment.\n"
                    "Une course déjà lancée n'apparaît que si le hub l'a vue avant son "
                    "départ. Savoir qu'un ami est en solo ou en essais libres n'est pas "
                    "possible.")
            return

        for enfant in self.liste_amis.winfo_children():
            enfant.destroy()
        for rang, (nom, epreuve) in enumerate(presences):
            ligne = ctk.CTkFrame(self.liste_amis, fg_color="transparent")
            ligne.grid(row=rang, column=0, sticky="ew", pady=2)
            ligne.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(ligne, text=nom, font=self.f["body"], text_color=theme.TEXT,
                         anchor="w", width=150).grid(row=0, column=0, sticky="w")

            detail = f"{epreuve.nom} · {epreuve.circuit}"
            ctk.CTkLabel(ligne, text=detail, font=self.f["small"],
                         text_color=theme.TEXT_DIM, anchor="w").grid(
                row=0, column=1, sticky="ew", padx=(12, 12))

            ctk.CTkLabel(ligne, text=epreuve.compte_a_rebours(), font=self.f["small"],
                         text_color=self._couleur_delai(epreuve), anchor="e",
                         width=110).grid(row=0, column=2, sticky="e")

    # --- tableau ---

    def _couleur_delai(self, epreuve):
        restant = epreuve.minutes_avant()
        if restant is None:
            return theme.TEXT_FAINT
        if restant <= 0 or epreuve.lancee:
            return theme.OK
        return theme.ACCENT if restant <= IMMINENT_MIN else theme.TEXT_DIM

    def _filtrees(self):
        choix = self.filtre.get()
        if choix == AVEC_AMIS:
            return [e for e in self.epreuves if e.amis]
        for niveau in NIVEAUX_FILTRES:
            if choix == cal.LIBELLES_NIVEAU[niveau]:
                return [e for e in self.epreuves if e.niveau == niveau]
        return list(self.epreuves)

    def appliquer(self):
        self.filtrees = self._filtrees()
        for enfant in self.liste.winfo_children():
            enfant.destroy()
        self.affichees = 0

        if not self.filtrees:
            self.plus.grid_forget()
            self._vider("Aucune épreuve ne correspond à ce filtre."
                        if self.epreuves else "Aucune épreuve à venir.")
            self._maj_ascenseur()
        else:
            self._afficher_bloc()
        self._maj_compteur()

    def afficher_plus(self):
        self._afficher_bloc()
        self._maj_compteur()

    def _afficher_bloc(self):
        bloc = self.filtrees[self.affichees:self.affichees + PAR_BLOC]
        for decalage, epreuve in enumerate(bloc):
            self._ligne(self.affichees + decalage, epreuve)
        self.affichees += len(bloc)

        reste = len(self.filtrees) - self.affichees
        if reste > 0:
            self.plus.configure(text=f"Afficher {min(reste, PAR_BLOC)} de plus"
                                     f"  ({reste} restantes)")
            self.plus.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 10))
        else:
            self.plus.grid_forget()
        self._maj_ascenseur()

    def _maj_compteur(self):
        avec = sum(1 for e in self.epreuves if e.amis)
        texte = f"{self.affichees} affichée(s) sur {len(self.filtrees)}"
        if avec:
            texte += f" · {avec} avec des amis"
        self.compteur.configure(text=texte)

    def _vider(self, message):
        for enfant in self.liste.winfo_children():
            enfant.destroy()
        etiquette = ctk.CTkLabel(self.liste, text=message, font=self.f["small"],
                                 text_color=theme.TEXT_FAINT, anchor="w",
                                 justify="left")
        etiquette.grid(row=0, column=0, sticky="ew", padx=16, pady=12)
        responsive.replier_texte(etiquette, self, marge=80)

    def _ligne(self, rang, epreuve):
        ligne = ctk.CTkFrame(self.liste, fg_color="transparent")
        ligne.grid(row=rang, column=0, sticky="ew", pady=1)
        self._configurer_grille(ligne)

        for colonne, (cle, _, _, _, _) in enumerate(self.visibles):
            texte, couleur = self._cellule(cle, epreuve)
            ctk.CTkLabel(ligne, text=texte, font=self.f["small"], text_color=couleur,
                         anchor="w").grid(row=0, column=colonne, sticky="ew",
                                          padx=(0, ESPACE), pady=4)

    def _cellule(self, cle, epreuve):
        if cle == "quand":
            return epreuve.compte_a_rebours(), self._couleur_delai(epreuve)
        if cle == "nom":
            return tronquer(epreuve.nom, self.largeurs["nom"]), theme.TEXT
        if cle == "circuit":
            return tronquer(epreuve.circuit, self.largeurs["circuit"]), theme.TEXT_DIM
        if cle == "niveau":
            return cal.LIBELLES_NIVEAU.get(epreuve.niveau, epreuve.niveau), theme.TEXT_DIM
        if cle == "inscrits":
            if epreuve.inscrits is None:
                return "—", theme.TEXT_FAINT
            detail = str(epreuve.inscrits)
            if epreuve.splits > 1:
                detail += f" · {epreuve.splits} splits"
            return detail, theme.ACCENT if epreuve.complet else theme.TEXT_DIM
        noms = ", ".join(a.nom for a in epreuve.amis)
        return ((tronquer(noms, self.largeurs["amis"]), theme.OK) if noms
                else ("—", theme.TEXT_FAINT))
