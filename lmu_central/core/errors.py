"""Exceptions communes au hub."""

DEFAULT_PORT = 6397


class HubError(RuntimeError):
    """Erreur affichable telle quelle a l'utilisateur."""


class GameNotRunningError(HubError):
    """Le jeu doit tourner pour cette operation."""

    def __init__(self, detail="", port=DEFAULT_PORT):
        self.detail = detail  # message systeme, conserve pour le debug
        message = (
            "Le Mans Ultimate ne repond pas sur le port {}.\n"
            "  Lance le jeu (le menu principal suffit) puis reessaie."
        ).format(port)
        super().__init__(message)


class BackendError(HubError):
    """Erreur renvoyee par raceos.gg."""
