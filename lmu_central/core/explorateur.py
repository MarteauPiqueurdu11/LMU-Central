"""Montrer un fichier dans l'Explorateur Windows.

`explorer /select,"<fichier>"` ouvre le dossier avec le fichier deja
selectionne : c'est ce qu'il faut pour arriver « pile » sur un setup, parmi les
dizaines de fichiers d'un meme circuit. Le hub ne fait que regarder — il
n'ouvre ni ne modifie le fichier.

L'Explorateur ne signale aucune de ses erreurs : il retombe ailleurs sans un
mot. D'ou deux precautions, prises ici plutot que par chaque appelant :

- le chemin est ramene a des antislashs, la seule forme que `/select` attend ;
- on verifie que le fichier existe. Sinon l'Explorateur ne rouvre pas son
  dossier : il ouvre le Bureau avec « Documents » surligne, comme si tout
  s'etait bien passe — constate, et deroutant pour qui cherche un setup.
"""

import os

from .errors import HubError


def _explorateur():
    """Chemin complet de explorer.exe.

    Un nom nu est cherche d'abord dans le dossier courant, qui est celui d'ou
    l'utilisateur a lance le programme — Telechargements, par exemple.
    """
    racine = os.environ.get("SystemRoot") or r"C:\Windows"
    return os.path.join(racine, "explorer.exe")


def montrer(chemin):
    """Ouvre l'Explorateur sur `chemin`, fichier selectionne. Renvoie ce chemin.

    Leve `HubError` si le fichier a disparu ou si l'Explorateur ne demarre pas.
    """
    fichier = os.path.normpath(os.path.abspath(str(chemin)))
    if not os.path.isfile(fichier):
        raise HubError(
            f"{os.path.basename(fichier)} n'existe plus.\n"
            "  Actualise la liste des setups pour la remettre à jour.")
    try:
        # Les guillemets vont apres la virgule, colles a elle : c'est la seule
        # forme qui survit aux espaces, virgules et parentheses des noms.
        os.startfile(_explorateur(), "open", f'/select,"{fichier}"')
    except OSError as exc:
        raise HubError(f"Impossible d'ouvrir l'Explorateur : {exc}") from exc
    return fichier
