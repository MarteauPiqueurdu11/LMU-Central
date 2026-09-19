"""
Theme sombre de l'application.

Palette a trois niveaux :
- noir  : les fonds, du plus profond (fenetre) au plus clair (champs)
- rouge : l'accent, reserve aux elements actifs et aux alertes
- blanc : le texte important et les etats valides

Les gris intermediaires ne sont pas une quatrieme couleur : ce sont des
transitions entre le noir et le blanc, pour hierarchiser le texte.

L'ensemble s'appuie sur le theme ttk "clam", le seul des themes fournis a
accepter une personnalisation complete des couleurs sous Windows.
"""

from tkinter import ttk

# -- Noirs ------------------------------------------------------------------
# Gris strictement neutres : la moindre dominante bleue vire au "bleu nuit"
# des que la surface s'eclaircit. Rouge, vert et bleu restent donc proches.
FENETRE = "#101011"      # fond general
SURFACE = "#212125"      # panneaux, onglets inactifs
CHAMP = "#3c3c43"        # zones de saisie, listes et boutons
SURVOL = "#4e4e57"       # survol des controles
BORDURE = "#404046"      # traits de separation
CONTOUR = "#6a6a73"      # contour des controles, pour les detacher du fond

# -- Rouge ------------------------------------------------------------------
ACCENT = "#c8102e"       # rouge Fanatec
ACCENT_VIF = "#e01a3c"   # survol
ACCENT_SOMBRE = "#8c0b20"  # enfonce

# -- Blancs et gris ---------------------------------------------------------
BLANC = "#ffffff"        # texte fort, etats valides
TEXTE = "#e5e5e7"        # texte courant
ATTENUE = "#9a9aa1"      # texte secondaire, aide
DISCRET = "#6b6b72"      # texte desactive

# -- Roles semantiques ------------------------------------------------------
# Le vert est volontairement absent : un etat valide se lit en blanc franc,
# une alerte ou une attente en rouge.
OK = BLANC
ALERTE = ACCENT_VIF
NEUTRE = ATTENUE

POLICE = "Segoe UI"
POLICE_MONO = "Consolas"


def appliquer(racine, changer_fond=True):
    """Applique le theme a une fenetre Tk et a tous ses widgets ttk.

    `changer_fond=False` laisse le fond de la fenetre intact : utile quand le
    theme est applique a une fenetre hote qui a deja le sien.
    """
    if changer_fond:
        racine.configure(bg=FENETRE)

    style = ttk.Style(racine)
    style.theme_use("clam")

    _conteneurs(style)
    _textes(style)
    _boutons(style)
    _champs(style, racine)
    _onglets(style)

    return style


def _conteneurs(style):
    style.configure("TFrame", background=FENETRE)
    style.configure("Surface.TFrame", background=SURFACE)
    style.configure("TSeparator", background=BORDURE)


def _textes(style):
    style.configure("TLabel", background=FENETRE, foreground=TEXTE,
                    font=(POLICE, 9))
    style.configure("Titre.TLabel", foreground=BLANC, font=(POLICE, 10, "bold"))
    style.configure("Aide.TLabel", foreground=ATTENUE, font=(POLICE, 8))
    style.configure("Entete.TLabel", foreground=ATTENUE,
                    font=(POLICE, 8, "bold"))
    style.configure("Position.TLabel", foreground=BLANC,
                    font=(POLICE, 10, "bold"))
    style.configure("Index.TLabel", foreground=TEXTE,
                    font=(POLICE_MONO, 10, "bold"))
    style.configure("Accent.TLabel", foreground=ACCENT_VIF, font=(POLICE, 9))


def _boutons(style):
    # Bouton courant : surface sombre, liseré discret, accent au survol.
    style.configure(
        "TButton",
        background=CHAMP,
        foreground=TEXTE,
        bordercolor=BORDURE,
        lightcolor=CHAMP,
        darkcolor=CHAMP,
        focuscolor=BORDURE,
        borderwidth=1,
        padding=(12, 6),
        font=(POLICE, 9),
    )
    style.map(
        "TButton",
        background=[("pressed", ACCENT_SOMBRE), ("active", SURVOL)],
        foreground=[("pressed", BLANC), ("active", BLANC)],
        bordercolor=[("active", ACCENT)],
    )

    # Action principale : rouge plein.
    style.configure(
        "Accent.TButton",
        background=ACCENT,
        foreground=BLANC,
        bordercolor=ACCENT,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
        font=(POLICE, 9, "bold"),
    )
    style.map(
        "Accent.TButton",
        background=[("pressed", ACCENT_SOMBRE), ("active", ACCENT_VIF)],
        bordercolor=[("active", ACCENT_VIF)],
    )

    # Boutons de tableau : compacts, pour ne pas alourdir les 12 lignes.
    style.configure("Compact.TButton", padding=(6, 3), font=(POLICE, 8))
    style.map(
        "Compact.TButton",
        background=[("pressed", ACCENT_SOMBRE), ("active", SURVOL)],
        foreground=[("pressed", BLANC), ("active", BLANC)],
        bordercolor=[("active", ACCENT)],
    )

    # En clam, la case est peinte par indicatorcolor et la coche par
    # indicatorforeground : sans quoi on obtient un aplat rouge illisible.
    style.configure(
        "TCheckbutton",
        background=FENETRE,
        foreground=TEXTE,
        focuscolor=FENETRE,
        indicatorcolor=CHAMP,
        indicatorforeground=BLANC,
        indicatorrelief="flat",
        bordercolor=BORDURE,
        padding=(2, 2),
        font=(POLICE, 9),
    )
    style.map(
        "TCheckbutton",
        background=[("active", FENETRE)],
        foreground=[("active", BLANC), ("selected", BLANC)],
        indicatorcolor=[("selected", ACCENT), ("active", SURVOL)],
        bordercolor=[("selected", ACCENT), ("active", ACCENT)],
    )


def _champs(style, racine):
    # Les champs n'ont pas de contour au repos : la bordure prend la couleur
    # du remplissage, et ne se revele qu'au survol ou a la saisie. C'est ce
    # qui distingue un champ moderne d'un champ ttk d'origine.
    style.configure(
        "TEntry",
        fieldbackground=CHAMP,
        foreground=TEXTE,
        insertcolor=BLANC,
        bordercolor=CHAMP,
        lightcolor=CHAMP,
        darkcolor=CHAMP,
        borderwidth=1,
        padding=(8, 6),
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", ACCENT), ("hover", SURVOL)],
        lightcolor=[("focus", ACCENT), ("hover", SURVOL)],
        darkcolor=[("focus", ACCENT), ("hover", SURVOL)],
        fieldbackground=[("focus", SURVOL)],
    )

    style.configure(
        "TCombobox",
        fieldbackground=CHAMP,
        background=CHAMP,
        foreground=TEXTE,
        arrowcolor=ATTENUE,
        bordercolor=CHAMP,
        lightcolor=CHAMP,
        darkcolor=CHAMP,
        borderwidth=1,
        arrowsize=12,
        padding=(8, 6),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", CHAMP), ("hover", SURVOL)],
        background=[("readonly", CHAMP), ("hover", SURVOL)],
        selectbackground=[("readonly", CHAMP)],
        selectforeground=[("readonly", TEXTE)],
        bordercolor=[("focus", ACCENT), ("hover", SURVOL)],
        lightcolor=[("focus", ACCENT), ("hover", SURVOL)],
        darkcolor=[("focus", ACCENT), ("hover", SURVOL)],
        arrowcolor=[("hover", BLANC), ("focus", ACCENT_VIF)],
    )

    # La liste deroulante d'un Combobox est une Listbox Tk classique : elle
    # echappe au style ttk et se configure par la base d'options.
    racine.option_add("*TCombobox*Listbox.background", CHAMP)
    racine.option_add("*TCombobox*Listbox.foreground", TEXTE)
    racine.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    racine.option_add("*TCombobox*Listbox.selectForeground", BLANC)
    racine.option_add("*TCombobox*Listbox.borderWidth", 0)
    racine.option_add("*TCombobox*Listbox.font", (POLICE, 9))


def _onglets(style):
    # Le cadre clair par defaut autour du contenu vient de bordercolor et des
    # reliefs light/dark : on les fond dans l'arriere-plan.
    style.configure(
        "TNotebook",
        background=FENETRE,
        bordercolor=FENETRE,
        lightcolor=FENETRE,
        darkcolor=FENETRE,
        borderwidth=0,
        tabmargins=(0, 4, 0, 0),
    )
    style.configure(
        "TNotebook.Tab",
        background=SURFACE,
        foreground=ATTENUE,
        bordercolor=FENETRE,
        lightcolor=SURFACE,
        darkcolor=SURFACE,
        borderwidth=0,
        padding=(18, 8),
        font=(POLICE, 9),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", CHAMP), ("active", SURVOL)],
        foreground=[("selected", BLANC), ("active", TEXTE)],
        expand=[("selected", (0, 0, 0, 0))],
    )
