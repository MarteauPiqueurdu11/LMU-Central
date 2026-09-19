"""Les deux vues interchangeables de la page Ratings : amis et historique."""

import customtkinter as ctk

from ..core import courses as courses_core
from ..core import historique as hist
from ..core.timefmt import local_time
from . import responsive, theme
from .widgets import FriendRow, tronquer

RANK_ORDER = ["Bronze", "Silver", "Gold", "Platinum"]

# Lignes ajoutees a chaque fois. Correspond a une page du backend, tiree pour
# chacun des types d'epreuve encore ouverts.
PAR_BLOC = 20

# Pages tirees au maximum pour un seul clic, quand un filtre restrictif ecarte
# tout ce qui arrive. Evite de boucler sur un filtre a une poignee de resultats.
PAGES_PAR_CLIC = 3

# Colonnes du tableau : cle, intitule, largeur, extensible, priorite.
# `priorite` dit ce qu'on sacrifie en premier quand la fenetre retrecit : 0 ne
# part jamais, 4 part en premier. La date et le DR restent donc toujours la.
COLONNES = (
    ("date",     "DATE",            64, 0, 0),
    ("titre",    "ÉPREUVE",        160, 1, 3),
    ("circuit",  "CIRCUIT",        130, 1, 4),
    ("position", "POS",             54, 0, 1),
    ("dr",       "DRIVER RATING",  146, 0, 0),
    ("sr",       "SAFETY RATING",  146, 0, 2),
)
ESPACE_COLONNE = 8      # padding horizontal entre deux colonnes
MARGE_TABLEAU = 54      # marges laterales du tableau, ascenseur compris

# Filtres par ligne selon la place disponible : on replie la barre au lieu de
# la laisser deborder.
PALIERS_FILTRES = (470, 810)
COLONNES_FILTRES = (1, 2, 4)


def _tri_ami(ami):
    dr = ami.get("driverRank") or {}
    rang = dr.get("rank", "Bronze")
    indice = RANK_ORDER.index(rang) if rang in RANK_ORDER else 0
    return (indice, dr.get("tier", 0), dr.get("progress", 0))


def _chevrons(crans):
    """Representation compacte du nombre de crans gagnes ou perdus."""
    if not crans:
        return "=", theme.TEXT_FAINT
    fleche = "▲" if crans > 0 else "▼"
    return fleche * min(abs(crans), 3), (theme.OK if crans > 0 else theme.ACCENT)


class VueAmis(ctk.CTkFrame):
    """Les amis Steam et leurs ratings."""

    # Colonnes secondaires, retirees quand la largeur ne suffit plus.
    PALIERS = (420, 620)

    def __init__(self, master, polices):
        super().__init__(master, fg_color="transparent")
        self.f = polices
        self.donnees = None
        self.palier = len(self.PALIERS)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        note = ctk.CTkLabel(
            self, text="Le serveur ne transmet leur progression que par tranches de 10 %.",
            font=self.f["tiny"], text_color=theme.TEXT_FAINT, anchor="w",
            justify="left")
        note.grid(row=0, column=0, sticky="ew", padx=20, pady=(0, 10))
        responsive.replier_texte(note, self, marge=48)

        self.entetes = ctk.CTkFrame(self, fg_color="transparent")
        self.entetes.grid(row=1, column=0, sticky="ew", padx=(6, 26))

        self.liste = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.liste.grid(row=2, column=0, sticky="nsew", padx=6, pady=(4, 12))
        self.liste.grid_columnconfigure(0, weight=1)
        self._maj_ascenseur = responsive.ascenseur_discret(self.liste, theme.SURFACE)

        self._construire_entetes()
        responsive.suivre_paliers(self, self.PALIERS, self._changer_palier)

    def _colonnes(self):
        """Colonnes affichees au palier courant, du nom vers l'accessoire."""
        return [("PILOTE", 1, 150), ("DRIVER RATING", 0, 130),
                ("SAFETY RATING", 0, 130), ("COURSES", 0, 80)][:self.palier + 2]

    def _construire_entetes(self):
        for enfant in self.entetes.winfo_children():
            enfant.destroy()
        colonnes = self._colonnes()
        derniere = len(colonnes) - 1
        for colonne, (texte, poids, largeur) in enumerate(colonnes):
            self.entetes.grid_columnconfigure(colonne, weight=poids, minsize=largeur)
            ctk.CTkLabel(self.entetes, text=texte, font=self.f["tiny"],
                         text_color=theme.TEXT_FAINT,
                         anchor="e" if texte == "COURSES" else "w").grid(
                row=0, column=colonne, sticky="ew",
                padx=(16, 8) if colonne == 0
                else ((8, 16) if colonne == derniere else 8))

    def _changer_palier(self, palier):
        self.palier = palier
        self._construire_entetes()
        if self.donnees is not None:
            self.remplir(self.donnees)

    def remplir(self, data):
        self.donnees = data
        for enfant in self.liste.winfo_children():
            enfant.destroy()
        amis = sorted(data.friends, key=_tri_ami, reverse=True)
        if not amis:
            ctk.CTkLabel(self.liste, text="Aucun ami à afficher.", font=self.f["small"],
                         text_color=theme.TEXT_FAINT, anchor="w").grid(
                row=0, column=0, sticky="ew", padx=16, pady=8)
            return
        colonnes = len(self._colonnes())
        self._maj_ascenseur()
        for rang, ami in enumerate(amis):
            FriendRow(self.liste, self.f, ami, data.races_of(ami.get("id")),
                      colonnes=colonnes).grid(row=rang, column=0, sticky="ew")


class VueCourses(ctk.CTkFrame):
    """L'historique des courses : 20 lignes, puis 20 de plus a la demande."""

    def __init__(self, master, polices, run_async, au_changement=None):
        super().__init__(master, fg_color="transparent")
        self.f = polices
        self.run_async = run_async
        self.au_changement = au_changement
        self.chargeur = None
        self.filtrees = []
        self.affichees = 0
        self.occupe = False
        self._cible = PAR_BLOC
        self.visibles = list(COLONNES)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._construire_filtres()

        self.resume = ctk.CTkLabel(self, text="", font=self.f["tiny"],
                                   text_color=theme.TEXT_FAINT, anchor="w")
        self.resume.grid(row=1, column=0, sticky="ew", padx=20, pady=(6, 6))
        responsive.replier_texte(self.resume, self, marge=48)

        self.entetes = ctk.CTkFrame(self, fg_color="transparent")
        self.entetes.grid(row=2, column=0, sticky="ew", padx=(20, 34))

        self.liste = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.liste.grid(row=3, column=0, sticky="nsew", padx=8, pady=(4, 6))
        self.liste.grid_columnconfigure(0, weight=1)
        self._maj_ascenseur = responsive.ascenseur_discret(self.liste, theme.SURFACE)

        self.plus = ctk.CTkButton(self, text="", height=30, corner_radius=6,
                                  font=self.f["small"], fg_color=theme.SURFACE_HI,
                                  hover_color=theme.BORDER, text_color=theme.TEXT_DIM,
                                  command=self.afficher_plus)

        self._construire_entetes()
        responsive.suivre_largeur(self, self._ajuster_colonnes)

    # --- filtres ---

    def _construire_filtres(self):
        self.barre = ctk.CTkFrame(self, fg_color="transparent")
        self.barre.grid(row=0, column=0, sticky="ew", padx=16)

        self.menus = {}
        self.blocs = []
        for cle, titre in (("titre", "Épreuve"), ("circuit", "Circuit"),
                           ("classe", "Classe"), ("resultat", "Résultat")):
            bloc = ctk.CTkFrame(self.barre, fg_color="transparent")
            bloc.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(bloc, text=titre.upper(), font=self.f["tiny"],
                         text_color=theme.TEXT_FAINT, anchor="w").grid(row=0, column=0,
                                                                       sticky="ew")
            menu = ctk.CTkOptionMenu(
                bloc, values=[courses_core.TOUS], width=155, height=28,
                corner_radius=6, font=self.f["small"], dropdown_font=self.f["small"],
                fg_color=theme.SURFACE_HI, button_color=theme.SURFACE_HI,
                button_hover_color=theme.BORDER, text_color=theme.TEXT,
                command=lambda _=None: self.appliquer())
            menu.grid(row=1, column=0, sticky="ew", pady=(2, 0))
            self.menus[cle] = menu
            self.blocs.append(bloc)

        self.raz = ctk.CTkButton(self.barre, text="Réinitialiser", width=100, height=28,
                                 corner_radius=6, font=self.f["small"],
                                 fg_color="transparent", hover_color=theme.SURFACE_HI,
                                 text_color=theme.TEXT_FAINT,
                                 command=self.reinitialiser)

        self._disposer_filtres(len(COLONNES_FILTRES) - 1)
        responsive.suivre_paliers(self.barre, PALIERS_FILTRES, self._disposer_filtres)

    def _disposer_filtres(self, palier):
        """Repartit les quatre filtres sur une, deux ou quatre colonnes."""
        par_ligne = COLONNES_FILTRES[palier]
        for colonne in range(5):
            self.barre.grid_columnconfigure(colonne, weight=0, minsize=0)
        for colonne in range(par_ligne):
            self.barre.grid_columnconfigure(colonne, weight=1, minsize=150)

        for indice, bloc in enumerate(self.blocs):
            bloc.grid(row=indice // par_ligne, column=indice % par_ligne,
                      sticky="ew", padx=(0, 10), pady=(0, 6))

        # Le bouton se glisse a cote des filtres tant qu'il reste de la place,
        # sinon il passe sous la derniere ligne.
        lignes = (len(self.blocs) + par_ligne - 1) // par_ligne
        if par_ligne == 4:
            self.raz.grid(row=0, column=4, sticky="sw", pady=(16, 6), padx=(0, 0))
        else:
            self.raz.grid(row=lignes, column=0, columnspan=par_ligne, sticky="w",
                          pady=(0, 6))

    # --- colonnes du tableau ---

    def _ajuster_colonnes(self, largeur):
        """Retire les colonnes accessoires tant que le tableau ne rentre pas."""
        retenues = list(COLONNES)
        while largeur > 1 and self._largeur_requise(retenues) > largeur:
            sacrifiee = max(retenues, key=lambda c: c[4])
            if sacrifiee[4] == 0:
                break
            retenues.remove(sacrifiee)

        if [c[0] for c in retenues] == [c[0] for c in self.visibles]:
            return
        self.visibles = retenues
        self._construire_entetes()
        self.appliquer(cible=self.affichees)

    @staticmethod
    def _largeur_requise(colonnes):
        return sum(c[2] for c in colonnes) + ESPACE_COLONNE * len(colonnes) + MARGE_TABLEAU

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
                row=0, column=colonne, sticky="ew", padx=(0, ESPACE_COLONNE))

    # --- chargement ---

    def demarrer(self, chargeur):
        """Premiere page : la vue s'affiche des les 20 premieres courses."""
        self.chargeur = chargeur
        if chargeur.tout_charge:
            # Repli hors ligne : les courses sont deja la, il n'y a rien a
            # tirer du reseau. _charger() ne ferait que renoncer, et la vue
            # resterait vide. Reste a rapprocher les releves locaux, qui
            # donnent les pourcentages exacts meme sans backend.
            courses_core.rapprocher(chargeur.courses, hist.variations(limite=500))
            self._recu(chargeur.courses)
            return
        self._charger(premier=True)

    def afficher_plus(self):
        """Affiche 20 lignes de plus, en allant les chercher si necessaire."""
        if len(self.filtrees) > self.affichees:
            self._afficher_bloc()
            return
        self._charger()

    def _charger(self, premier=False):
        if self.occupe or self.chargeur is None or self.chargeur.tout_charge:
            return
        self.occupe = True
        # Un chargement declenche par le bouton doit montrer un bloc de plus
        # qu'avant, pas se contenter de redessiner l'existant.
        self._cible = PAR_BLOC if premier else self.affichees + PAR_BLOC
        self.plus.configure(text="Chargement…", state="disabled")
        if premier:
            self.resume.configure(text="Chargement des courses…")

        # Les widgets Tk ne se lisent que depuis le thread graphique : on releve
        # les filtres ici, avant de partir en tache de fond.
        filtres = self._filtres_courants()
        cible = len(self.filtrees) + PAR_BLOC
        self.run_async(lambda: self._travail(filtres, cible), self._recu, self._echec)

    def _travail(self, filtres, cible):
        """Tire des pages jusqu'a avoir de quoi remplir un bloc."""
        for _ in range(PAGES_PAR_CLIC):
            self.chargeur.page_suivante()
            courses_core.rapprocher(self.chargeur.courses, hist.variations(limite=500))
            if self.chargeur.tout_charge:
                break
            if len(courses_core.filtrer(self.chargeur.courses, **filtres)) >= cible:
                break
        return self.chargeur.courses

    def _echec(self, exc):
        self.occupe = False
        self.plus.configure(text="Réessayer", state="normal")
        self.resume.configure(text=str(exc).replace("\n", " ")[:120])

    def indisponible(self, exc):
        """Ni backend joignable, ni course en cache : il faut le dire.

        Un panneau vide laisse croire a un bug ; on explique ce qui manque et
        ce qui debloquerait la situation.
        """
        self.chargeur = None
        self.filtrees = []
        self.affichees = 0
        for enfant in self.liste.winfo_children():
            enfant.destroy()
        self.plus.grid_forget()

        ctk.CTkLabel(
            self.liste, justify="left", anchor="w", font=self.f["small"],
            text_color=theme.TEXT_DIM,
            text="Aucune course en mémoire.\n\n"
                 "Lance Le Mans Ultimate, puis reviens ici : l'historique sera "
                 "chargé,\net gardé pour les fois suivantes — même jeu fermé.").grid(
            row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        ctk.CTkLabel(
            self.liste, text=str(exc).replace("\n", " ")[:160], anchor="w",
            font=self.f["tiny"], text_color=theme.TEXT_FAINT).grid(
            row=1, column=0, sticky="ew", padx=16, pady=(0, 10))

        self.resume.configure(text="Historique indisponible")
        if self.au_changement:
            self.au_changement([], 0)

    def _recu(self, courses):
        self.occupe = False
        self.plus.configure(state="normal")
        for cle, attribut in (("titre", "titre"), ("circuit", "circuit"),
                              ("classe", "classe")):
            valeurs = courses_core.valeurs(courses, attribut)
            actuel = self.menus[cle].get()
            self.menus[cle].configure(values=valeurs)
            self.menus[cle].set(actuel if actuel in valeurs else courses_core.TOUS)
        self.menus["resultat"].configure(values=list(courses_core.RESULTATS))
        self.appliquer(cible=self._cible)

    # --- filtres et affichage ---

    def _filtres_courants(self):
        """Etat des menus, sous forme d'arguments pour courses_core.filtrer."""
        return {"epreuve": self.menus["titre"].get(),
                "circuit": self.menus["circuit"].get(),
                "classe": self.menus["classe"].get(),
                "resultat": self.menus["resultat"].get()}

    def _filtrer(self, courses):
        return courses_core.filtrer(courses, **self._filtres_courants())

    def reinitialiser(self):
        for menu in self.menus.values():
            menu.set(courses_core.TOUS)
        self.appliquer()

    def appliquer(self, cible=None):
        """Recalcule la liste filtree et redessine `cible` lignes (20 par defaut)."""
        self.filtrees = self._filtrer(self.chargeur.courses if self.chargeur else [])

        for enfant in self.liste.winfo_children():
            enfant.destroy()
        self.affichees = 0
        self._afficher_bloc(cible or PAR_BLOC)
        self._maj_resume()

    def _afficher_bloc(self, combien=PAR_BLOC):
        bloc = self.filtrees[self.affichees:self.affichees + combien]
        for decalage, course in enumerate(bloc):
            self._ligne(self.affichees + decalage, course)
        self.affichees += len(bloc)

        if not self.filtrees:
            vide = ("Aucune course ne correspond aux filtres."
                    if self.chargeur is not None and self.chargeur.courses
                    else "Aucune course chargée.")
            ctk.CTkLabel(self.liste, text=vide, font=self.f["small"],
                         text_color=theme.TEXT_FAINT, anchor="w").grid(
                row=0, column=0, sticky="ew", padx=16, pady=10)

        self._maj_ascenseur()
        self._maj_bouton()
        if self.au_changement:
            self.au_changement(self.filtrees, self.affichees)

    def _maj_bouton(self):
        reste = len(self.filtrees) - self.affichees
        if reste > 0:
            self.plus.configure(text=f"Afficher {min(reste, PAR_BLOC)} de plus"
                                     f"  ({reste} en reserve)")
        elif self.chargeur is not None and not self.chargeur.tout_charge:
            self.plus.configure(text="Charger les courses suivantes")
        else:
            self.plus.grid_forget()
            return
        self.plus.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 10))

    def _maj_resume(self):
        total = len(self.chargeur.courses) if self.chargeur else 0
        retenues = len(self.filtrees)
        exactes = sum(1 for c in self.filtrees if c.exacte)

        texte = ""
        if getattr(self.chargeur, "hors_ligne", False):
            quand = local_time(self.chargeur.date) if self.chargeur.date else "?"
            texte = f"Hors ligne — dernier chargement du {quand} · "

        texte += f"{retenues} course(s)" + (f" sur {total} chargées" if retenues != total else "")
        if self.filtrees:
            texte += (f" · du {local_time(self.filtrees[-1].date)[:10]}"
                      f" au {local_time(self.filtrees[0].date)[:10]}")
        if self.chargeur is not None and not self.chargeur.tout_charge:
            texte += " · d'autres disponibles"
        texte += (f" · {exactes} avec le DR et le SR exacts" if exactes
                  else " · pourcentages exacts à partir des prochaines courses")
        self.resume.configure(text=texte)

    # --- une ligne ---

    def _ligne(self, rang, course):
        ligne = ctk.CTkFrame(self.liste, fg_color="transparent")
        ligne.grid(row=rang, column=0, sticky="ew", pady=1)
        self._configurer_grille(ligne)

        for colonne, (cle, _, largeur, _, _) in enumerate(self.visibles):
            texte, couleur = self._cellule(cle, course, largeur)
            ctk.CTkLabel(ligne, text=texte, font=self.f["small"], text_color=couleur,
                         anchor="w").grid(row=0, column=colonne, sticky="ew",
                                          padx=(0, ESPACE_COLONNE), pady=4)

    def _cellule(self, cle, course, largeur):
        """Contenu et couleur d'une cellule, selon la colonne."""
        if cle == "date":
            return local_time(course.date)[:5], theme.TEXT_DIM
        if cle == "titre":
            return tronquer(course.titre, largeur), theme.TEXT
        if cle == "circuit":
            return tronquer(course.circuit, largeur), theme.TEXT_DIM
        if cle == "position":
            return self._texte_position(course)
        if cle == "dr":
            return self._texte_variation(course, course.dr_crans, "dr_pct")
        return self._texte_variation(course, course.sr_crans, "sr_pct")

    @staticmethod
    def _texte_position(course):
        if course.abandon:
            return course.statut.upper(), theme.ACCENT
        texte = f"P{course.position}"
        if str(course.grille).isdigit() and course.rang:
            gagne = int(course.grille) - course.rang
            if gagne:
                texte += f"  {gagne:+d}"   # places gagnees depuis la grille
        return texte, (theme.OK if course.victoire else theme.TEXT)

    @staticmethod
    def _texte_variation(course, crans, attribut):
        """Pourcentage exact si l'historique le couvre, sinon les crans."""
        fleche, couleur = _chevrons(crans)
        if course.variation is None:
            return fleche, couleur
        pct = getattr(course.variation, attribut)
        couleur = theme.OK if pct > 0 else (theme.ACCENT if pct < 0 else theme.TEXT_FAINT)
        if course.exacte:
            return f"{fleche}  {pct:+.2f} %", couleur
        # Plusieurs courses tombent dans le meme intervalle de releve : l'ecart
        # les concerne toutes, on ne peut pas l'attribuer a une seule.
        return f"{fleche}  {pct:+.2f} % ({course.variation_partagee}×)", theme.TEXT_DIM
