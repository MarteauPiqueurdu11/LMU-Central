"""Client du backend en ligne RaceOS (raceos.gg) de Le Mans Ultimate.

Chaine d'authentification reproduite depuis l'interface web du jeu :
  1. le jeu fournit un ticket de session Steam via son API locale
  2. POST /authenticate echange ce ticket contre un accessToken
     -- la reponse contient deja le profil complet, ratings inclus
  3. les RPC suivants utilisent l'en-tete Game-Authorization

Toutes les operations de ce module sont en LECTURE SEULE.
"""

import json
import urllib.error
import urllib.request

from . import cache
from .errors import BackendError
from .localapi import LocalAPI

RACEOS_HOST = "https://raceos.gg"
GAME = "lmu"
PLATFORM = "steam"


class RaceOS:
    def __init__(self, local_api=None, timeout=20):
        self.local = local_api or LocalAPI()
        self.timeout = timeout
        self.access_token = None
        self.expires_at = None
        self.player = None
        self.banned = False
        # Vrai quand le dernier appel a authenticate() a reellement relu le
        # profil aupres du serveur, faux s'il a rendu une valeur memorisee.
        self.profil_relu = False
        self.profil_date = None  # date de capture du profil courant

    # --- transport ---

    def _request(self, url, method="POST", body=None, headers=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        hdrs = {"Content-Type": "application/json"}
        hdrs.update(headers or {})
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise BackendError(f"raceos.gg a repondu {exc.code} {exc.reason} — {detail}") from exc
        except urllib.error.URLError as exc:
            raise BackendError(f"raceos.gg injoignable ({getattr(exc, 'reason', exc)})") from exc
        return json.loads(raw) if raw.strip() else None

    # --- authentification ---

    def authenticate(self, force=False):
        """Authentifie le joueur et renvoie son profil complet.

        L'accessToken reste valable 30 minutes et est mis en cache : pendant ce
        laps de temps, le hub fonctionne meme si le jeu a ete ferme. Passe ce
        delai, le jeu doit etre relance — le backend n'offre aucun mecanisme de
        renouvellement, seul le jeu peut fournir un nouveau ticket Steam.

        Attention au profil rendu sans `force` : c'est celui du dernier relevé,
        fige. Une course disputee entre-temps ne s'y voit pas — seul un nouvel
        appel a /authenticate publie le rating a jour, et il reclame le jeu.
        L'appelant lit `profil_relu` pour savoir a quoi il a affaire.
        """
        if self.player is not None and not force:
            self.profil_relu = False
            return self.player

        if not force:
            session = cache.load_session()
            if session:
                self.access_token = session["accessToken"]
                self.expires_at = session["expiresAt"]
                self.player = session["player"]
                self.profil_relu = False
                self.profil_date = session.get("fetchedAt")
                return self.player

        body = {"token": self.local.auth_session_ticket(), "game": GAME, "platform": PLATFORM}
        payload = self._request(f"{RACEOS_HOST}/authenticate", body=body) or {}
        self.access_token = payload.get("accessToken")
        if not self.access_token:
            raise BackendError("Authentification refusee par raceos.gg.")
        self.expires_at = payload.get("expiresAt")
        self.player = payload.get("player") or {}
        self.banned = payload.get("banned", False)
        self.profil_relu = True
        self.profil_date = cache.save_session(self.access_token, self.expires_at,
                                              self.player)
        return self.player

    def fetch(self, endpoint, body=None, method="POST"):
        """Appelle un RPC RaceOS authentifie."""
        self.authenticate()
        headers = {"Game-Authorization": f"Bearer {self.access_token}"}
        return self._request(f"{RACEOS_HOST}/{endpoint.lstrip('/')}",
                             method=method, body=body, headers=headers)

    # --- lectures ---

    def friends(self, sync=False):
        """Amis Steam avec leurs ratings (ELO masque par le serveur).

        `sync` demande au backend de **relire** la liste depuis Steam au lieu
        de servir celle qu'il garde en memoire. Le jeu s'en charge quand on
        ouvre ses ecrans multijoueur ; un compte qui n'a fait que se
        connecter — exactement ce que le hub demande — peut donc n'avoir
        jamais ete synchronise, et sa liste reste vide.

        On ne reclame la synchronisation que si la liste revient vide : c'est
        le seul cas ou il n'y a de toute facon rien a montrer, et cela evite
        d'imposer ce travail au serveur a chaque consultation.
        """
        amis = self._friends(sync)
        if amis or sync:
            return amis
        return self._friends(True)

    def _friends(self, sync):
        return self.fetch("api/v1/player/friends-list",
                          body={"platform": PLATFORM, "game": GAME,
                                "sync": sync}) or []

    def statistics(self, player_ids):
        """Courses et victoires, pour un ou plusieurs joueurs."""
        if not player_ids:
            return {}
        return self.fetch("api/v1/statistics/overall",
                          body={"game": GAME, "playerIds": list(player_ids)}) or {}
