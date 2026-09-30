"""Driver Rating et Safety Rating exacts.

Le jeu n'affiche la progression que par tranches de 10 %. Le serveur, lui,
renvoie la valeur precise pour le joueur authentifie.

Limite connue : pour tout autre joueur, le serveur remet `elo` et `rating` a 0
et arrondit `progress` a la dizaine. Cette censure a lieu cote serveur, avant
l'envoi — elle n'est pas contournable.
"""

import json

from ..core import ratings as ratings_core
from ..ui import console as ui
from .base import Module

RANK_ORDER = ["Bronze", "Silver", "Gold", "Platinum"]


def _sort_key(driver):
    dr = driver.get("driverRank") or {}
    rank = dr.get("rank", "Bronze")
    idx = RANK_ORDER.index(rank) if rank in RANK_ORDER else 0
    return (idx, dr.get("tier", 0), dr.get("progress", 0))


class RatingsModule(Module):
    name = "ratings"
    title = "Driver & Safety Rating"
    description = "Ton DR / SR au centieme de pourcent, et ceux de tes amis"
    order = 10
    # Une session en cache ou un instantane suffisent : le jeu n'est pas
    # toujours necessaire, c'est authenticate() qui tranche.
    requires_game = False

    def add_arguments(self, parser):
        parser.add_argument("--friends", action="store_true",
                            help="afficher aussi les amis Steam")
        parser.add_argument("--json", action="store_true",
                            help="sortie JSON brute, pour scripter")
        parser.add_argument("--refresh", action="store_true",
                            help="forcer une nouvelle authentification (jeu requis)")

    def run(self, args, ctx):
        data = ratings_core.load(ctx, with_friends=args.friends, refresh=args.refresh)

        if args.json:
            print(json.dumps({"player": data.player, "friends": data.friends,
                              "statistics": data.statistics,
                              "fetchedAt": data.fetched_at},
                             indent=2, ensure_ascii=False))
            return 0

        if data.offline:
            ui.title("HORS LIGNE")
            ui.note(f"Jeu ferme et session expiree — dernieres valeurs connues, "
                    f"{ui.local_time(data.fetched_at)}.")
            ui.note("Relance Le Mans Ultimate pour rafraichir.")
        elif data.profil_date:
            # Amis et statistiques sont frais, le profil non : seul
            # /authenticate donne le rating exact, et il exige le jeu.
            ui.title("PROFIL DATE")
            ui.note(f"Ton DR et ton SR datent de {ui.local_time(data.profil_date)} "
                    f"— le jeu est ferme.")
            ui.note("Relance Le Mans Ultimate pour la valeur d'apres ta course.")

        self._show_player(data.player, data.my_stats())
        if args.friends:
            if data.friends:
                self._show_friends(data.friends, data.statistics)
            elif data.offline:
                ui.title("AMIS STEAM")
                ui.note("Aucun ami dans l'instantane : relance avec le jeu ouvert.")
        print()
        return 0

    def _show_player(self, player, stats):
        dr = player.get("driverRank") or {}
        sr = player.get("safetyRank") or {}

        ui.title(player.get("name") or player.get("username") or "?")
        if stats:
            races, wins = stats.get("races", 0), stats.get("wins", 0)
            rate = (wins / races * 100) if races else 0
            ui.note(f"{races} courses · {wins} victoires ({rate:.1f} %)")

        ui.rating_block("DRIVER RATING", dr.get("rank", "?"), dr.get("tier", 0),
                        dr.get("progress", 0.0), "ELO", dr.get("elo", 0.0))
        ui.rating_block("SAFETY RATING", sr.get("rank", "?"), sr.get("tier", 0),
                        sr.get("progress", 0.0), "Rating", sr.get("rating", 0.0))

        ratio = sr.get("contactImpactsPerLapRatio")
        if ratio:
            history = sr.get("contactImpactsPerLapRatios") or []
            suffix = f" · sur {len(history)} courses" if history else ""
            ui.note(f"Contacts par tour {ratio:.3f}{suffix}")

    def _show_friends(self, friends, stats):
        ui.title(f"AMIS STEAM ({len(friends)})")
        ui.note("Le serveur masque l'ELO des autres joueurs : progression arrondie a 10 %.")
        print()
        for f in sorted(friends, key=_sort_key, reverse=True):
            dr = f.get("driverRank") or {}
            sr = f.get("safetyRank") or {}
            name = (f.get("name") or f.get("username") or "?")[:22]
            races = stats.get(f.get("id"), {}).get("races", 0)
            drc, src = ui.rank_color(dr.get("rank")), ui.rank_color(sr.get("rank"))
            dr_label = "{:<8} {}".format(dr.get("rank", "?"), dr.get("tier", "?"))
            sr_label = "{:<8} {}".format(sr.get("rank", "?"), sr.get("tier", "?"))
            print(
                f"  {name:<22}"
                f"   DR {ui.c(dr_label, drc)} ~{dr.get('progress', 0):>3.0f} %"
                f"   SR {ui.c(sr_label, src)} ~{sr.get('progress', 0):>3.0f} %"
                f"   {ui.c(str(races) + ' courses', ui.DIM)}"
            )
