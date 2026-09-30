"""Chargement des ratings, partage par la ligne de commande et l'interface.

Strategie en trois temps :
  1. jeu ouvert         -> valeurs fraiches, mises en cache
  2. session < 30 min   -> valeurs fraiches sans le jeu
  3. sinon              -> dernier instantane connu, date
"""

from . import cache, historique
from .errors import GameNotRunningError


class Ratings:
    """Resultat d'un chargement de ratings."""

    def __init__(self, player, friends, statistics, fetched_at=None,
                 profil_date=None):
        self.player = player or {}
        self.friends = friends or []
        self.statistics = statistics or {}
        self.fetched_at = fetched_at  # non nul = donnees hors ligne
        # Non nul = le profil n'a pas ete relu a l'instant, et porte donc la
        # date de son dernier relevé. Les amis et les courses, eux, viennent
        # bien du reseau : les deux fraicheurs ne vont pas toujours ensemble.
        self.profil_date = profil_date

    @property
    def offline(self):
        return self.fetched_at is not None

    @property
    def driver_rank(self):
        return self.player.get("driverRank") or {}

    @property
    def safety_rank(self):
        return self.player.get("safetyRank") or {}

    @property
    def name(self):
        return self.player.get("name") or self.player.get("username") or "?"

    def my_stats(self):
        return self.statistics.get(self.player.get("id")) or {}

    def races_of(self, player_id):
        return (self.statistics.get(player_id) or {}).get("races", 0)


def _profil(ros, refresh):
    """Le profil du joueur, et la date de sa capture s'il n'a pas ete relu.

    Seul /authenticate publie le rating exact, et il reclame un ticket Steam :
    jeu ferme, le profil ne peut pas etre rafraichi, meme quand la session est
    encore valide. On sert alors la valeur connue en disant son age, plutot
    que de faire echouer un chargement dont les amis et les courses, eux,
    restent parfaitement joignables.
    """
    if refresh:
        try:
            return ros.authenticate(force=True), None
        except GameNotRunningError:
            pass

    player = ros.authenticate()
    return player, None if ros.profil_relu else ros.profil_date


def load(ctx, with_friends=True, refresh=False):
    """Charge les ratings, avec repli hors ligne.

    Leve GameNotRunningError seulement si aucune donnee n'est disponible.
    """
    try:
        ros = ctx.raceos
        player, profil_date = _profil(ros, refresh)
        friends = ros.friends() if with_friends else []
        ids = [player["id"]] + [f["id"] for f in friends]
        statistics = ros.statistics(ids)
        cache.save_snapshot({"player": player, "friends": friends,
                             "statistics": statistics})
        resultat = Ratings(player, friends, statistics, profil_date=profil_date)
        # Le pourcentage exact n'existe que dans cette reponse : on le releve
        # a chaque passage pour pouvoir mesurer les ecarts plus tard.
        historique.enregistrer(resultat)
        return resultat
    except GameNotRunningError:
        snapshot = cache.load_snapshot()
        if not snapshot:
            raise
        return Ratings(snapshot.get("player"), snapshot.get("friends"),
                       snapshot.get("statistics"), snapshot.get("fetchedAt"))
