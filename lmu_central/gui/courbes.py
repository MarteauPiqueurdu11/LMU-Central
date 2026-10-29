"""Vue « Courbes » de la page Ratings : le DR ou le SR dans le temps.

L'axe vertical est la position absolue dans l'echelle des rangs, chaque tier
valant 100 points : (indice_rang * 3 + tier - 1) * 100 + progression. L'ELO
n'est pas utilise, faute de seuils publies pour le convertir en rang.

Rien ne tourne en tache de fond : la vue ne se redessine que quand on la
redimensionne, qu'on change de filtre ou que la page appelle `recharger()`.
"""

import bisect
import datetime
import math
import tkinter as tk

import customtkinter as ctk

from ..core import historique
from . import theme

RANGS = ["Bronze", "Silver", "Gold", "Platinum"]

DR, SR = "Driver Rating", "Safety Rating"

# cle du rang, du tier, de la progression, de la valeur exacte, et son nom
MESURES = {
    DR: ("drRank", "drTier", "drProgress", "drElo", "ELO"),
    SR: ("srRank", "srTier", "srProgress", "srRating", "Rating"),
}

PERIODES = {"7 j": 7, "30 j": 30, "90 j": 90, "Tout": None}
PERIODE_DEFAUT = "30 j"

# Marges du trace dans le canevas, en pixels : a gauche, les libelles de tier,
# en bas, les dates.
MARGE_G, MARGE_D, MARGE_H, MARGE_B = 34, 14, 12, 26

ECART_DATES = 110      # pixels minimum entre deux dates
HAUTEUR_LIBELLE = 14   # hauteur de bande minimum pour ecrire « G1 »
MAX_PASTILLES = 200    # au-dela, les pastilles ne font plus que du bruit
ANTI_RAFALE = 40       # millisecondes

# Pas possibles entre deux dates, en heures.
PAS_HEURES = (1, 2, 3, 6, 12, 24, 48, 72, 24 * 7, 24 * 14, 24 * 30, 24 * 60,
              24 * 90, 24 * 180, 24 * 365)

MSG_VIDE = ("Pas encore de relevé. La courbe se remplit à chaque course suivie "
            "par le hub : laisse-le ouvert pendant que tu joues.")
MSG_PERIODE = "Aucun relevé sur cette période."


def _melanger(couleur, fond, part):
    """`part` de `couleur` sur `fond`, en hexadecimal."""
    a = [int(couleur[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(fond[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * part + y * (1 - part)):02X}"
                         for x, y in zip(a, b))


def _date(point):
    try:
        moment = datetime.datetime.fromisoformat(
            str(point.get("date")).replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment


def _absolu(rang, tier, progression):
    return (RANGS.index(rang) * 3 + tier - 1) * 100 + (progression or 0)


def _rang_de(position):
    """Rang et tier de la bande qui contient `position`."""
    case = max(0, min(int(position // 100), len(RANGS) * 3 - 1))
    return RANGS[case // 3], case % 3 + 1


class VueCourbes(ctk.CTkFrame):
    """La courbe du DR ou du SR, sur fond de bandes de rang."""

    def __init__(self, master, polices):
        super().__init__(master, fg_color="transparent")
        self.f = polices
        self.releves = []
        self._serie = []       # (date, position, point, ecart) de la periode
        self._ecran = []       # (x, y) de chaque point de la serie
        self._xs = []
        self._attente = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        barre = ctk.CTkFrame(self, fg_color="transparent")
        barre.grid(row=0, column=0, sticky="ew", padx=16, pady=(0, 8))
        barre.grid_columnconfigure(1, weight=1)

        style = dict(font=self.f["small"], height=30, corner_radius=8,
                     selected_color=theme.ACCENT, selected_hover_color=theme.ACCENT_HI,
                     unselected_color=theme.SURFACE_HI,
                     unselected_hover_color=theme.BORDER, text_color=theme.TEXT)

        self.choix_mesure = ctk.CTkSegmentedButton(
            barre, values=list(MESURES), command=lambda _: self._redessiner(), **style)
        self.choix_mesure.grid(row=0, column=0, sticky="w")
        self.choix_mesure.set(DR)

        self.choix_periode = ctk.CTkSegmentedButton(
            barre, values=list(PERIODES), command=lambda _: self._redessiner(), **style)
        self.choix_periode.grid(row=0, column=2, sticky="e")
        self.choix_periode.set(PERIODE_DEFAUT)

        self.resume = ctk.CTkLabel(self, text="", font=self.f["tiny"],
                                   text_color=theme.TEXT_DIM, anchor="w")
        self.resume.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 6))

        self.canevas = tk.Canvas(self, bg=theme.SURFACE, height=260,
                                 highlightthickness=0, bd=0)
        self.canevas.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 14))
        self.canevas.bind("<Configure>", self._sur_redimension)
        self.canevas.bind("<Motion>", self._survol)
        self.canevas.bind("<Leave>", lambda _: self.canevas.delete("survol"))

    # --- donnees ---

    def recharger(self):
        """Relit l'historique et redessine."""
        self.releves = historique.points()
        self._redessiner()

    def _calculer_serie(self):
        """Les points de la periode choisie, avec leur ecart au precedent.

        L'ecart se calcule sur tout l'historique : le premier point de la
        periode garde ainsi son ecart avec le releve qui le precede.
        """
        cle_rang, cle_tier, cle_prog, _, _ = MESURES[self.choix_mesure.get()]
        jours = PERIODES[self.choix_periode.get()]
        debut = (datetime.datetime.now(datetime.timezone.utc)
                 - datetime.timedelta(days=jours)) if jours else None

        serie, precedente = [], None
        for point in self.releves:
            moment = _date(point)
            rang, tier = point.get(cle_rang), point.get(cle_tier)
            if moment is None or rang not in RANGS or not tier:
                continue
            position = _absolu(rang, tier, point.get(cle_prog))
            ecart = None if precedente is None else position - precedente
            precedente = position
            if debut is None or moment >= debut:
                serie.append((moment, position, point, ecart))
        return serie

    # --- dessin ---

    def _sur_redimension(self, _event):
        if self._attente:
            self.after_cancel(self._attente)
        self._attente = self.after(ANTI_RAFALE, self._redessiner)

    def _redessiner(self):
        self._attente = None
        c = self.canevas
        c.delete("all")
        self._ecran, self._xs = [], []
        self._serie = self._calculer_serie()
        self._maj_resume()

        largeur, hauteur = c.winfo_width(), c.winfo_height()
        if largeur < 60 or hauteur < 60:
            return
        if not self._serie:
            c.create_text(largeur / 2, hauteur / 2, text=MSG_PERIODE if self.releves
                          else MSG_VIDE, fill=theme.TEXT_DIM, font=self.f["small"],
                          width=min(largeur - 40, 460), justify="center")
            return

        x0, x1 = MARGE_G, largeur - MARGE_D
        y0, y1 = MARGE_H, hauteur - MARGE_B

        positions = [s[1] for s in self._serie]
        bas = math.floor(min(positions) / 100) * 100
        haut = math.ceil(max(positions) / 100) * 100
        if haut <= bas:
            haut = bas + 100

        def y_de(position):
            return y1 - (position - bas) / (haut - bas) * (y1 - y0)

        t_debut, t_fin = self._serie[0][0], self._serie[-1][0]
        duree = (t_fin - t_debut).total_seconds()

        def x_de(moment):
            if duree <= 0:
                return (x0 + x1) / 2
            return x0 + (moment - t_debut).total_seconds() / duree * (x1 - x0)

        self._dessiner_bandes(bas, haut, y_de, x0, x1)
        self._dessiner_dates(t_debut, t_fin, duree, x_de, x0, x1, y0, y1)

        self._ecran = [(x_de(m), y_de(p)) for m, p, _, _ in self._serie]
        self._xs = [x for x, _ in self._ecran]
        if len(self._ecran) > 1:
            c.create_line(*[v for xy in self._ecran for v in xy], fill="#FFFFFF",
                          width=2, joinstyle="round", capstyle="round")
        if len(self._ecran) <= MAX_PASTILLES:
            for (x, y), (_, position, _, _) in zip(self._ecran, self._serie):
                couleur = theme.rank_color(_rang_de(position)[0])
                c.create_oval(x - 3.5, y - 3.5, x + 3.5, y + 3.5,
                              fill=couleur, outline=couleur)

    def _dessiner_bandes(self, bas, haut, y_de, x0, x1):
        """Une bande par tier, puis les separations : pleines entre deux rangs,
        pointillees entre deux tiers."""
        c = self.canevas
        for case in range(int(bas // 100), int(haut // 100)):
            rang, tier = RANGS[case // 3], case % 3 + 1
            couleur = theme.rank_color(rang)
            haut_bande, bas_bande = y_de((case + 1) * 100), y_de(case * 100)
            c.create_rectangle(x0, haut_bande, x1, bas_bande, width=0,
                               fill=_melanger(couleur, theme.SURFACE,
                                              0.17 if tier % 2 else 0.10))
            if bas_bande - haut_bande >= HAUTEUR_LIBELLE:
                c.create_text(x0 - 6, (haut_bande + bas_bande) / 2,
                              text=f"{rang[0]}{tier}", anchor="e",
                              fill=couleur, font=self.f["tiny"])
            if tier == 1:
                c.create_line(x0, bas_bande, x1, bas_bande, fill=couleur, width=2)
            else:
                c.create_line(x0, bas_bande, x1, bas_bande, dash=(4, 4),
                              fill=_melanger(couleur, theme.SURFACE, 0.45))

    def _dessiner_dates(self, t_debut, t_fin, duree, x_de, x0, x1, y0, y1):
        c = self.canevas
        grille = _melanger(theme.BORDER, theme.SURFACE, 0.5)
        format_date = "%d/%m %Hh" if duree < 3 * 86400 else "%d/%m"

        if duree <= 0:
            c.create_text((x0 + x1) / 2, y1 + 6, anchor="n", fill=theme.TEXT_FAINT,
                          text=t_debut.astimezone().strftime(format_date),
                          font=self.f["tiny"])
            return

        pixels_par_heure = (x1 - x0) / (duree / 3600)
        pas = next((h for h in PAS_HEURES if h * pixels_par_heure >= ECART_DATES),
                   PAS_HEURES[-1])

        # Premier repere rond, en heure locale : minuit pour les pas en jours,
        # une heure multiple du pas sinon.
        local = t_debut.astimezone()
        if pas >= 24:
            repere = local.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            repere = local.replace(minute=0, second=0, microsecond=0)
            repere -= datetime.timedelta(hours=repere.hour % pas)
        while repere < local:
            repere += datetime.timedelta(hours=pas)

        dernier_x = None
        while repere <= t_fin:
            x = x_de(repere)
            if dernier_x is None or x - dernier_x >= ECART_DATES:
                c.create_line(x, y0, x, y1, fill=grille)
                c.create_text(x, y1 + 6, anchor="n", fill=theme.TEXT_FAINT,
                              text=repere.strftime(format_date), font=self.f["tiny"])
                dernier_x = x
            repere = (repere + datetime.timedelta(hours=pas)).astimezone()

    def _maj_resume(self):
        if not self._serie:
            self.resume.configure(text="")
            return
        positions = [s[1] for s in self._serie]
        gain = positions[-1] - positions[0]
        sommet = max(positions)
        rang, tier = _rang_de(sommet)
        n = len(self._serie)
        self.resume.configure(
            text=f"{n} relevé{'s' if n > 1 else ''} · {gain:+.2f} % sur la période · "
                 f"plus haut {rang} {tier} · {sommet % 100:.2f} %")

    # --- survol ---

    def _survol(self, event):
        c = self.canevas
        c.delete("survol")
        if not self._xs:
            return

        i = bisect.bisect_left(self._xs, event.x)
        if i >= len(self._xs) or (i > 0 and event.x - self._xs[i - 1] < self._xs[i] - event.x):
            i -= 1
        x, y = self._ecran[i]
        moment, position, point, ecart = self._serie[i]
        _, _, _, cle_valeur, nom_valeur = MESURES[self.choix_mesure.get()]
        rang, tier = _rang_de(position)
        couleur = theme.rank_color(rang)

        hauteur = c.winfo_height()
        c.create_line(x, MARGE_H, x, hauteur - MARGE_B, dash=(3, 3),
                      fill=theme.TEXT_FAINT, tags="survol")
        c.create_oval(x - 5, y - 5, x + 5, y + 5, fill=couleur, outline="#FFFFFF",
                      width=2, tags="survol")

        valeur = point.get(cle_valeur) or 0
        lignes = [
            moment.astimezone().strftime("%d/%m/%Y %H:%M"),
            f"{rang} {tier} · {position % 100:.2f} %",
            f"{nom_valeur} {valeur:.2f}" if nom_valeur == "ELO" else f"{nom_valeur} {valeur:.3f}",
            "Premier relevé" if ecart is None
            else f"{ecart:+.2f} % depuis le relevé précédent",
        ]
        texte = c.create_text(0, 0, text="\n".join(lignes), anchor="nw",
                              fill=theme.TEXT, font=self.f["tiny"], tags="survol")
        g, h, d, b = c.bbox(texte)
        l, ht = d - g + 16, b - h + 12

        bx = x + 12 if x + 12 + l <= c.winfo_width() else x - 12 - l
        by = min(max(y - ht / 2, 2), hauteur - ht - 2)
        c.coords(texte, bx + 8, by + 6)
        fond = c.create_rectangle(bx, by, bx + l, by + ht, fill=theme.BG,
                                  outline=theme.BORDER, tags="survol")
        c.tag_lower(fond, texte)
