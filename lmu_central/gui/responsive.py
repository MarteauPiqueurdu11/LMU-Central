"""Adaptation des pages a la taille de la fenetre.

Tk ne reorganise rien tout seul. Une grille dont les colonnes ont un `minsize`
ne retrecit pas : elle deborde de son conteneur, et le contenu est coupe sans
le moindre avertissement. Une barre de defilement horizontale reglerait le
symptome, mais lire un tableau en le faisant glisser est penible.

On ecoute donc la largeur reelle et on reorganise : moins de colonnes, filtres
sur deux lignes, cartes empilees. Le defilement vertical, lui, reste la bonne
reponse quand c'est la hauteur qui manque.
"""

import tkinter


def suivre_largeur(widget, rappel, marge=16, delai=60):
    """Appelle `rappel(largeur)` a chaque changement notable de largeur.

    `<Configure>` part en rafale pendant un redimensionnement : on ignore les
    variations de moins de `marge` pixels et on attend que la rafale se calme
    avant de rappeler, pour ne pas reconstruire l'interface a chaque pixel.
    """
    etat = {"largeur": -1, "attente": None}

    def declencher():
        etat["attente"] = None
        if widget.winfo_exists():
            rappel(widget.winfo_width())

    def au_configure(evenement):
        if abs(evenement.width - etat["largeur"]) < marge:
            return
        etat["largeur"] = evenement.width
        if etat["attente"] is not None:
            widget.after_cancel(etat["attente"])
        etat["attente"] = widget.after(delai, declencher)

    widget.bind("<Configure>", au_configure, add="+")


def suivre_paliers(widget, paliers, rappel, **kwargs):
    """Comme `suivre_largeur`, mais ne rappelle que si l'on change de palier.

    `paliers` est une suite croissante de largeurs. Le rappel recoit l'indice
    du palier courant : 0 pour l'affichage le plus etroit, len(paliers) pour
    le plus large. Evite de reconstruire un tableau pour dix pixels.
    """
    etat = {"palier": None}

    def au_changement(largeur):
        palier = sum(1 for seuil in paliers if largeur >= seuil)
        if palier == etat["palier"]:
            return
        etat["palier"] = palier
        rappel(palier)

    suivre_largeur(widget, au_changement, **kwargs)


def replier_texte(label, reference, marge=44, minimum=180):
    """Fait passer un long texte a la ligne au lieu d'elargir son conteneur.

    Un CTkLabel sans `wraplength` reclame toute sa phrase sur une seule ligne :
    il gonfle la carte qui le porte et pousse ses voisines hors de la fenetre.
    On suit donc la largeur d'un ancetre dont la taille, elle, est imposee de
    l'exterieur — sinon la mesure se mordrait la queue.
    """
    def ajuster(largeur):
        # Les etiquettes se recreent a chaque rafraichissement : sans cette
        # garde, un rappel survivrait a son etiquette et leverait a chaque
        # redimensionnement.
        if label.winfo_exists():
            label.configure(wraplength=max(minimum, largeur - marge))

    suivre_largeur(reference, ajuster)


def ascenseur_discret(cadre, fond):
    """Fond le curseur de defilement dans le decor tant que tout y tient.

    CustomTkinter 6 affiche son ascenseur en permanence : un filet vertical
    inutile au bord d'un menu de deux entrees ou d'une liste courte.

    On ne le retire pas de la grille, malgre l'envie : le retirer elargit la
    toile, et CustomTkinter ne la retrecit pas quand on le remet — le contenu
    finit alors coupe sous l'ascenseur. On le repeint donc de la couleur du
    fond, ce qui ne deplace rien.

    On se branche sur `yscrollcommand` de la toile plutot que sur
    `<Configure>` : Tk l'appelle a chaque fois que la portion visible change,
    y compris quand c'est la zone defilante qui grandit.
    """
    barre = getattr(cadre, "_scrollbar", None)
    toile = getattr(cadre, "_parent_canvas", None)
    if barre is None or toile is None:
        return

    vives = (barre.cget("button_color"), barre.cget("button_hover_color"))
    etat = {"visible": None}

    def relayer(debut, fin):
        barre.set(debut, fin)
        visible = not (float(debut) <= 0.0 and float(fin) >= 1.0)
        if visible == etat["visible"]:
            return
        etat["visible"] = visible
        barre.configure(button_color=vives[0] if visible else fond,
                        button_hover_color=vives[1] if visible else fond)

    def evaluer():
        if not toile.winfo_exists():
            return
        try:
            # `yview()` lit la geometrie. Sans ce recalcul, un appel fait juste
            # apres avoir ajoute des lignes decrit encore l'etat d'avant, et la
            # decision porte sur une liste qui n'existe plus.
            toile.update_idletasks()
            relayer(*toile.yview())
        except tkinter.TclError:
            pass  # fenetre en cours de fermeture

    def planifier(_=None):
        # `yview()` n'est juste qu'une fois la geometrie recalculee, d'ou le
        # passage par after_idle.
        if cadre.winfo_exists():
            cadre.after_idle(evaluer)

    toile.configure(yscrollcommand=relayer)
    # Tk n'appelle yscrollcommand que lorsque la portion visible change. Quand
    # tout tient des le depart, ou quand le contenu change sans que la fraction
    # bouge, il ne l'appelle pas : l'ascenseur resterait a sa couleur d'origine.
    # On surveille donc aussi les redimensionnements, et on rend `planifier`
    # pour que l'appelant force une reevaluation apres avoir redessine.
    toile.bind("<Configure>", planifier, add="+")
    cadre.bind("<Configure>", planifier, add="+")
    planifier()
    return planifier


def largeur_disponible(widget, marge=0):
    """Largeur utile d'un conteneur, une fois la fenetre reellement dessinee.

    Avant le premier affichage Tk renvoie 1 : on rend alors None, pour que
    l'appelant garde sa disposition par defaut au lieu de tout replier.
    """
    largeur = widget.winfo_width()
    return None if largeur <= 1 else max(0, largeur - marge)
