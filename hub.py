"""LMU Central — boite a outils Le Mans Ultimate.

    py -3 hub.py                  etat du jeu et modules disponibles
    py -3 hub.py ratings          ton DR / SR exact
    py -3 hub.py ratings --friends

Ajouter une fonctionnalite : deposer un fichier dans lmu_central/modules/
definissant une sous-classe de Module. Le hub la detecte tout seul.
"""

import argparse
import sys

from lmu_central.core import cache
from lmu_central.core.errors import HubError
from lmu_central.modules import Context, discover
from lmu_central.ui import console as ui

# Fonctionnalites prevues, affichees sur l'ecran d'accueil.
ROADMAP = [
    ("overlays", "Overlays de telemetrie en direct, personnalisables"),
]


def show_hub(modules, ctx):
    ui.title("LMU CENTRAL")

    try:
        state = ctx.local.game_state()
        where = state.get("gameState") or state.get("status") or "?"
        detail = "en course" if where not in ("Setup", "?") else "menus"
        ui.note(f"Le Mans Ultimate : {ui.c('lance', ui.GREEN)} · {detail} ({where})")
    except HubError:
        ui.note(f"Le Mans Ultimate : {ui.c('ferme', ui.RED)}")

    minutes = cache.session_expiry()
    if minutes:
        ui.note(f"Session RaceOS : encore {minutes:.0f} min — consultable sans le jeu")
    else:
        ui.note("Session RaceOS : expiree — lance le jeu pour rafraichir")

    ui.section("MODULES")
    for m in modules:
        label = "{:<18}".format(m.name)
        print(f"  {ui.c(label, ui.BOLD + ui.BLUE)}  {m.description}")

    if ROADMAP:
        ui.section("A VENIR")
        for name, desc in ROADMAP:
            label = "{:<18}".format(name)
            print(f"  {ui.c(label, ui.DIM)}  {ui.c(desc, ui.DIM)}")

    ui.section("USAGE")
    ui.note(f"py -3 hub.py <module> [options]   ·   py -3 hub.py {modules[0].name} --help"
            if modules else "Aucun module installe.")
    print()


def main(argv=None):
    modules = discover()

    # Options acceptees aussi bien avant qu'apres la sous-commande.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--no-color", action="store_true", help="desactiver les couleurs")
    common.add_argument("--port", type=int, default=None,
                        help="port de l'API locale du jeu (defaut 6397)")

    parser = argparse.ArgumentParser(
        prog="hub.py",
        description="LMU Central — boite a outils Le Mans Ultimate",
        parents=[common],
    )

    subparsers = parser.add_subparsers(dest="module")
    for m in modules:
        sub = subparsers.add_parser(m.name, help=m.description,
                                    description=m.title, parents=[common])
        m.add_arguments(sub)

    args = parser.parse_args(argv)
    ui.setup(color=not args.no_color)
    ctx = Context(port=args.port)

    if not args.module:
        show_hub(modules, ctx)
        return 0

    module = next(m for m in modules if m.name == args.module)
    try:
        if module.requires_game and not ctx.local.is_running():
            raise HubError(
                "Le Mans Ultimate ne repond pas sur le port 6397.\n"
                "  Lance le jeu (le menu principal suffit) puis reessaie."
            )
        return module.run(args, ctx)
    except HubError as exc:
        ui.error(str(exc))
        return 1
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    sys.exit(main())
