"""Decouverte automatique des modules du hub."""

import importlib
import inspect
import pkgutil

from .base import Context, Module

__all__ = ["Context", "Module", "discover"]


def discover():
    """Retourne une instance de chaque Module trouve dans ce package."""
    found = []
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_") or info.name == "base":
            continue
        mod = importlib.import_module(f"{__name__}.{info.name}")
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, Module) and obj is not Module and obj.__module__ == mod.__name__:
                found.append(obj())
    found.sort(key=lambda m: (m.order, m.name))
    return found
