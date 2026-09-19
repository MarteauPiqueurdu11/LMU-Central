"""Genere assets/icon.ico : le carre arrondi perce, aux couleurs du jeu.

La forme est celle de l'icone livree avec CustomTkinter (MIT, Tom Schimansky) :
un carre arrondi perce en son centre, avec son epaisseur en relief sur la
droite. On la reprend telle quelle et on n'en change que les couleurs — rouge
Le Mans Ultimate en facade, blanc pour le relief.

Recoloration plutot que redessin : le relief est un decalage subtil, et une
forme redessinee « a peu pres » se verrait. Chaque pixel est reclasse selon sa
luminosite entre les deux bleus d'origine, puis repeint sur la nouvelle paire.
La transparence est conservee telle quelle : c'est elle qui porte le trou
central et l'anticrenelage des bords.

Les deux couches recoivent un degrade, eclairees depuis le haut a gauche. Celui
du relief descend jusqu'a un gris franc : sans lui, sur le fond blanc de
l'explorateur de fichiers, le relief disparaitrait et il ne resterait qu'un
« C » rouge au lieu du carre perce.
"""

import sys
from pathlib import Path

from PIL import Image

# Les deux bleus de l'icone d'origine : facade et relief.
SOURCE_FACADE = (2, 156, 255)
SOURCE_RELIEF = (0, 98, 177)

# Leurs remplacantes, du point le plus eclaire au plus ombre. Le rouge est
# celui du logo officiel du jeu, eclairci puis assombri autour de #FF1D43.
FACADE_CLAIRE = (255, 74, 106)
FACADE_OMBRE = (214, 8, 48)
RELIEF_CLAIR = (255, 255, 255)
RELIEF_OMBRE = (148, 163, 180)

# Part de la position horizontale dans le degrade : 0 = lumiere strictement
# verticale, 0,5 = diagonale franche.
BIAIS = 0.30

SIZES = [16, 24, 32, 48, 64, 128, 256]


def luminosite(couleur):
    r, v, b = couleur[:3]
    return 0.299 * r + 0.587 * v + 0.114 * b


def melange(depart, arrivee, part):
    part = min(1.0, max(0.0, part))
    return tuple(round(depart[i] + (arrivee[i] - depart[i]) * part) for i in range(3))


def icone_source():
    """L'icone de CustomTkinter, dans sa plus grande definition."""
    try:
        import customtkinter
    except ImportError:
        print("customtkinter est requis pour regenerer l'icone.")
        return None

    chemin = (Path(customtkinter.__file__).parent / "assets" / "icons"
              / "CustomTkinter_icon_Windows.ico")
    if not chemin.exists():
        print("icone d'origine introuvable :", chemin)
        return None

    image = Image.open(chemin)
    image.size = max(image.info.get("sizes") or [(256, 256)])
    image.load()
    return image.convert("RGBA")


def recolorer(image):
    """Repeint les bleus en rouge et blanc, sans toucher a la transparence."""
    basse, haute = luminosite(SOURCE_RELIEF), luminosite(SOURCE_FACADE)
    etendue = haute - basse

    acces = image.load()
    largeur, hauteur = image.size
    sortie = []

    for y in range(hauteur):
        for x in range(largeur):
            r, v, b, a = acces[x, y]
            if a == 0:
                sortie.append((0, 0, 0, 0))
                continue

            # Position dans le degrade : lumiere venue du haut a gauche.
            part = (1 - BIAIS) * (y / (hauteur - 1)) + BIAIS * (x / (largeur - 1))
            facade = melange(FACADE_CLAIRE, FACADE_OMBRE, part)
            relief = melange(RELIEF_CLAIR, RELIEF_OMBRE, part)

            # 0 = aussi sombre que le relief d'origine, 1 = aussi clair que la
            # facade. Les valeurs intermediaires sont l'anticrenelage.
            couche = min(1.0, max(0.0, (luminosite((r, v, b)) - basse) / etendue))
            sortie.append(melange(relief, facade, couche) + (a,))

    resultat = Image.new("RGBA", image.size)
    resultat.putdata(sortie)
    return resultat


def logo(taille=256):
    """Le logo recolore, a la taille demandee. None si la source manque."""
    source = icone_source()
    return None if source is None else recolorer(source).resize(
        (taille, taille), Image.LANCZOS)


def main():
    source = icone_source()
    if source is None:
        return 1

    marque = recolorer(source)
    sortie = Path(__file__).parent / "assets" / "icon.ico"
    sortie.parent.mkdir(exist_ok=True)

    # Une image par definition : Windows pioche la bonne selon le contexte, et
    # une reduction soignee vaut mieux qu'un 256 px redimensionne a la volee.
    tailles = [marque.resize((t, t), Image.LANCZOS) for t in SIZES]
    tailles[-1].save(sortie, format="ICO", sizes=[(t, t) for t in SIZES])

    # Version PNG, pour l'interface et tout ce qui ne lit pas le .ico.
    marque.resize((256, 256), Image.LANCZOS).save(sortie.parent / "logo.png")

    print("icone generee :", sortie)
    print("logo genere   :", sortie.parent / "logo.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
