"""Socle des modules du hub.

Ajouter une fonctionnalite = deposer un fichier dans lmu_central/modules/ qui
definit une sous-classe de Module. Elle est decouverte et branchee sur la
ligne de commande automatiquement, sans toucher au reste du code.
"""

from ..core.localapi import LocalAPI
from ..core.raceos import RaceOS


class Context:
    """Ressources partagees entre modules, instanciees a la demande.

    L'authentification RaceOS n'a lieu qu'une fois par execution, meme si
    plusieurs modules la reclament.
    """

    def __init__(self, port=None):
        self._port = port
        self._local = None
        self._raceos = None

    @property
    def local(self):
        if self._local is None:
            self._local = LocalAPI(port=self._port) if self._port else LocalAPI()
        return self._local

    @property
    def raceos(self):
        if self._raceos is None:
            self._raceos = RaceOS(local_api=self.local)
        return self._raceos


class Module:
    """Une fonctionnalite du hub."""

    name = ""           # nom de la sous-commande
    title = ""          # intitule affiche
    description = ""    # une ligne d'explication
    requires_game = True  # le jeu doit-il tourner ?
    order = 100         # ordre d'affichage dans le hub

    def add_arguments(self, parser):
        """Options propres au module (optionnel)."""

    def run(self, args, ctx):
        """Execute le module. Retourne un code de sortie."""
        raise NotImplementedError
