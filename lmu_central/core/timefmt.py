"""Formatage des horodatages, partage par la ligne de commande et l'interface."""

import datetime


def local_time(iso):
    """Convertit un horodatage ISO en heure locale lisible."""
    try:
        moment = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return str(iso)
    return moment.astimezone().strftime("%d/%m/%Y à %Hh%M")
