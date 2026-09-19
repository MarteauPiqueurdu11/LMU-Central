"""Decouverte automatique des pages de l'interface."""

import importlib
import inspect
import pkgutil

from .base import Page

__all__ = ["Page", "discover"]


def discover():
    """Retourne les classes de pages trouvees dans ce package, triees."""
    found = []
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_") or info.name == "base":
            continue
        mod = importlib.import_module(f"{__name__}.{info.name}")
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, Page) and obj is not Page and obj.__module__ == mod.__name__:
                found.append(obj)
    found.sort(key=lambda p: (p.order, p.name))
    return found
