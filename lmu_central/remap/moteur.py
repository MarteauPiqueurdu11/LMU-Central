"""
Moteur du remap : lecture du volant, envoi des raccourcis, overlay.

Volontairement independant de l'interface : l'application appelle
`Moteur.poll()` a intervalle regulier et lit les evenements renvoyes.

Chaque position declenche une combinaison clavier. Une version precedente
passait par une manette Xbox virtuelle (pilote ViGEmBus), car LMU semblait
ignorer les frappes synthetiques ; le vrai obstacle etait en fait l'elevation
de privileges, et l'application lancee en administrateur atteint le jeu
directement.
"""

import time
import tkinter as tk

import keyboard
import pygame

from . import theme


def init_pygame():
    """Initialise pygame une seule fois."""
    if not pygame.get_init():
        pygame.init()
    if not pygame.joystick.get_init():
        pygame.joystick.init()


def lister_joysticks():
    """Renvoie les joysticks branches, sous forme (index, nom, nb_boutons)."""
    init_pygame()
    pygame.joystick.quit()
    pygame.joystick.init()

    resultat = []
    for i in range(pygame.joystick.get_count()):
        js = pygame.joystick.Joystick(i)
        js.init()
        resultat.append((i, js.get_name(), js.get_numbuttons()))
    return resultat


def ouvrir_tous():
    """Renvoie tous les joysticks branches, initialises et prets a etre lus."""
    init_pygame()
    pygame.joystick.quit()
    pygame.joystick.init()

    joysticks = []
    for i in range(pygame.joystick.get_count()):
        js = pygame.joystick.Joystick(i)
        js.init()
        joysticks.append(js)
    return joysticks


def trouver_volants(boutons_requis):
    """Renvoie TOUS les joysticks ayant assez de boutons.

    Un volant Fanatec expose plusieurs peripheriques HID (base et roue, par
    exemple) portant le meme nom mais un nombre de boutons different. Impossible
    de deviner lequel porte quel bouton : on les surveille donc tous, et un
    bouton est considere enfonce des qu'un des peripheriques le signale.
    """
    init_pygame()
    pygame.joystick.quit()
    pygame.joystick.init()

    besoin = max(boutons_requis) + 1 if boutons_requis else 1

    resultat = []
    for i in range(pygame.joystick.get_count()):
        js = pygame.joystick.Joystick(i)
        js.init()
        if js.get_numbuttons() >= besoin:
            resultat.append(js)
    return resultat


class Molette:
    """Une molette crantee : son compteur et ses actions."""

    def __init__(self, config_molette, config_globale, indice):
        self.config = config_molette
        self.globale = config_globale
        self.indice = indice
        self.position = config_molette["position_depart"]
        self.active = False
        self._precedent = {}

    @property
    def nom(self):
        return self.config["nom"]

    @property
    def configuree(self):
        """True si les boutons indispensables sont renseignes."""
        boutons = self.config["boutons"]
        return all(boutons.get(c) is not None
                   for c in ("increment", "decrement", "confirm"))

    def indices_boutons(self):
        return [v for v in self.config["boutons"].values() if v is not None]

    # -- cycle de vie --------------------------------------------------------

    def activer(self):
        self.active = True
        self.position = self.config["position_depart"]
        self._precedent = {}

    def liberer(self):
        self.active = False
        self._precedent = {}

    # -- lecture -------------------------------------------------------------

    def lire(self, joysticks):
        """Renvoie la liste des evenements produits par cette molette."""
        evenements = []
        etats = self._lire_etats(joysticks)
        nb = self.config["nb_positions"]

        if self._front("increment", etats):
            self.position = self.position + 1 if self.position < nb else 1
            evenements.append(("position", self.indice, self.position))

        if self._front("decrement", etats):
            self.position = self.position - 1 if self.position > 1 else nb
            evenements.append(("position", self.indice, self.position))

        if self._front("confirm", etats):
            libelle = self.declencher(self.position)
            evenements.append(("action", self.indice, self.position, libelle))

        self._precedent = etats
        return evenements

    def _lire_etats(self, joysticks):
        """Un bouton est enfonce des qu'au moins un peripherique le signale."""
        etats = {}
        for nom, index in self.config["boutons"].items():
            if index is None:
                etats[nom] = False
                continue
            etats[nom] = any(
                js.get_button(index)
                for js in joysticks
                if index < js.get_numbuttons()
            )
        return etats

    def _front(self, nom, etats):
        """True au moment precis ou le bouton passe de relache a enfonce."""
        return etats.get(nom, False) and not self._precedent.get(nom, False)

    # -- actions -------------------------------------------------------------

    def declencher(self, position):
        """Envoie l'action d'une position, quelle que soit la position courante.

        Utilise par la lecture du volant, et par le bouton "Envoyer" de
        l'interface pour binder dans une appli tierce.
        """
        action = self.config["actions"].get(str(position))
        if action is None:
            return "(non configuree)"
        if not action["touches"]:
            return "(aucune touche definie)"

        self._envoyer_touches(action["touches"])
        return action["libelle"]

    def _envoyer_touches(self, combinaison):
        """Maintient la combinaison un court instant avant de la relacher.

        keyboard.send() enfonce et relache dans la foulee ; certaines interfaces
        de capture de raccourci ne voient pas une frappe aussi breve.
        """
        duree = self.globale.get("duree_touche", 0.06)
        try:
            keyboard.press(combinaison)
            time.sleep(duree)
        finally:
            keyboard.release(combinaison)


class Moteur:
    """Pilote l'ensemble des molettes et la lecture des peripheriques."""

    def __init__(self, configuration):
        self.config = configuration
        self.joysticks = []
        self.actif = False
        self.molettes = [
            Molette(m, configuration, i)
            for i, m in enumerate(configuration["molettes"])
        ]

    # -- verifications -------------------------------------------------------

    def collisions_touches(self):
        """Combinaisons employees par plusieurs positions.

        Deux positions sur le meme raccourci declencheraient la meme action :
        c'est presque toujours une erreur de saisie.
        """
        vues = {}
        collisions = set()
        for molette in self.molettes:
            if not molette.configuree:
                continue
            for position, action in molette.config["actions"].items():
                touches = action["touches"].strip().lower()
                if not touches:
                    continue
                repere = (molette.indice, position)
                if touches in vues and vues[touches] != repere:
                    collisions.add(touches)
                vues[touches] = repere
        return sorted(collisions)

    # -- cycle de vie --------------------------------------------------------

    def demarrer(self):
        """Accroche le volant et arme la lecture des molettes.

        Renvoie (True, message) si tout est pret, (False, message) sinon.
        """
        if self.actif:
            return True, "Deja demarre."

        actives = [m for m in self.molettes if m.configuree]
        if not actives:
            return False, ("Aucune molette configuree. Renseigne au moins "
                           "Molette +, Molette - et Confirmation.")

        indices = [i for m in actives for i in m.indices_boutons()]
        self.joysticks = trouver_volants(indices)
        if not self.joysticks:
            besoin = max(indices) + 1
            return False, (f"Aucun peripherique avec au moins {besoin} boutons. "
                           "Volant branche et allume ?")

        for molette in actives:
            molette.activer()

        self.actif = True
        detail = f"{len(actives)} molette(s), {len(self.joysticks)} peripherique(s)"
        return True, f"Actif - {detail}"

    def arreter(self):
        self.actif = False
        for molette in self.molettes:
            molette.liberer()
        self.joysticks = []

    # -- boucle --------------------------------------------------------------

    def poll(self):
        """Scrute le volant et renvoie la liste des evenements.

        ("position", indice_molette, position)
        ("action", indice_molette, position, libelle)
        ("erreur", message)
        """
        if not self.actif or not self.joysticks:
            return []

        try:
            pygame.event.pump()
            evenements = []
            for molette in self.molettes:
                if molette.active:
                    evenements.extend(molette.lire(self.joysticks))
            return evenements
        except pygame.error:
            self.arreter()
            return [("erreur", "Volant perdu.")]


class Overlay(tk.Toplevel):
    """Fenetre sans bordure affichee par-dessus le jeu.

    Deux modes :
    - compact : une seule ligne par molette, juste la position courante
    - complet : la liste des positions, la courante surlignee
    """

    FOND = theme.SURFACE
    TEXTE = theme.ATTENUE
    ACTIVE = theme.BLANC
    ACCENT = theme.ACCENT_VIF
    POLICE = theme.POLICE_MONO

    def __init__(self, parent, configuration, au_deplacement=None):
        super().__init__(parent)
        self.config_app = configuration
        self.au_deplacement = au_deplacement
        self.courantes = {}

        reglages = configuration["overlay"]
        self.compact = reglages.get("compact", True)

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", reglages["opacite"])
        self.configure(bg=self.FOND)
        self.geometry(f"+{reglages['x']}+{reglages['y']}")

        marge = 6 if self.compact else 10
        cadre = tk.Frame(self, bg=self.FOND, padx=marge, pady=marge - 2)
        cadre.pack()

        self.lignes = {}
        self._widgets = [self, cadre]

        for indice, molette in enumerate(configuration["molettes"]):
            self.courantes[indice] = molette["position_depart"]
            if self.compact:
                self._construire_compact(cadre, indice, molette, reglages)
            else:
                self._construire_complet(cadre, indice, molette, reglages)

        self._depart = (0, 0)

        if reglages["clic_traversant"]:
            self.after(80, self._activer_clic_traversant)
        else:
            for widget in self._widgets:
                widget.bind("<Button-1>", self._debut_glisser)
                widget.bind("<B1-Motion>", self._glisser)

        self.rafraichir()

    def _construire_compact(self, cadre, indice, molette, reglages):
        """Une ligne : nom de la molette, puis position et libelle courants."""
        taille = reglages["taille_police"]

        rangee = tk.Frame(cadre, bg=self.FOND)
        rangee.pack(fill="x")

        etiquette = tk.Label(
            rangee,
            text=self._abreger(molette["nom"]),
            font=(self.POLICE, max(taille - 2, 6), "bold"),
            fg=self.ACCENT,
            bg=self.FOND,
        )
        etiquette.pack(side="left", padx=(0, 6))

        valeur = tk.Label(
            rangee,
            text="",
            font=(self.POLICE, taille),
            fg=self.ACTIVE,
            bg=self.FOND,
            anchor="w",
        )
        valeur.pack(side="left")

        self.lignes[indice] = valeur
        self._widgets.extend([rangee, etiquette, valeur])

    def _construire_complet(self, cadre, indice, molette, reglages):
        """La liste des positions, avec en-tete par molette."""
        taille = reglages["taille_police"]

        if indice > 0:
            espace = tk.Frame(cadre, bg=self.FOND, height=6)
            espace.pack(fill="x")
            self._widgets.append(espace)

        entete = tk.Label(
            cadre,
            text=molette["nom"].upper(),
            font=(self.POLICE, max(taille - 2, 6), "bold"),
            fg=self.ACCENT,
            bg=self.FOND,
            anchor="w",
        )
        entete.pack(fill="x", pady=(0, 3))
        self._widgets.append(entete)

        self.lignes[indice] = {}
        for position in sorted(molette["actions"], key=int):
            ligne = tk.Label(
                cadre,
                text="",
                font=(self.POLICE, taille),
                fg=self.TEXTE,
                bg=self.FOND,
                anchor="w",
            )
            ligne.pack(fill="x")
            self.lignes[indice][int(position)] = ligne
            self._widgets.append(ligne)

    @staticmethod
    def _abreger(nom):
        """"Molette 1" -> "M1", pour tenir sur une ligne etroite."""
        mots = nom.split()
        if len(mots) == 2 and mots[1].isdigit():
            return f"{mots[0][0].upper()}{mots[1]}"
        return nom.upper()[:8]

    def maj(self, indice, position_courante):
        self.courantes[indice] = position_courante
        self._dessiner(indice)

    def rafraichir(self):
        """A appeler quand les libelles ont ete modifies dans l'interface."""
        for indice in self.lignes:
            self._dessiner(indice)

    def _dessiner(self, indice):
        actions = self.config_app["molettes"][indice]["actions"]
        courante = self.courantes.get(indice)

        if self.compact:
            libelle = actions.get(str(courante), {}).get("libelle", "-")
            self.lignes[indice].configure(text=f"{courante:>2}  {libelle}")
            return

        for position, ligne in self.lignes[indice].items():
            libelle = actions.get(str(position), {}).get("libelle", f"Position {position}")
            if position == courante:
                ligne.configure(fg=self.ACTIVE, text=f"> {position:>2}  {libelle}")
            else:
                ligne.configure(fg=self.TEXTE, text=f"   {position:>2}  {libelle}")

    # -- deplacement ---------------------------------------------------------

    def _debut_glisser(self, event):
        self._depart = (event.x_root - self.winfo_x(), event.y_root - self.winfo_y())

    def _glisser(self, event):
        x = event.x_root - self._depart[0]
        y = event.y_root - self._depart[1]
        self.geometry(f"+{x}+{y}")
        self.config_app["overlay"]["x"] = x
        self.config_app["overlay"]["y"] = y
        if self.au_deplacement:
            self.au_deplacement()

    def _activer_clic_traversant(self):
        import ctypes

        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020

        hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
        styles = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, styles | WS_EX_LAYERED | WS_EX_TRANSPARENT
        )
