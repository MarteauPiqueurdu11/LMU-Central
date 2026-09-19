"""Client du serveur REST local de Le Mans Ultimate (127.0.0.1:6397).

Le jeu expose son interface web et 179 endpoints REST auto-documentes
(http://127.0.0.1:6397/swagger/). Ce client couvre ce dont le hub a besoin ;
les autres endpoints restent accessibles via `get()`.
"""

import json
import urllib.error
import urllib.request

from .errors import GameNotRunningError, HubError

DEFAULT_PORT = 6397


class LocalAPI:
    def __init__(self, port=DEFAULT_PORT, timeout=10):
        self.port = port
        self.timeout = timeout
        self.base = f"http://127.0.0.1:{port}"

    def get(self, path, raw=False):
        """GET sur l'API locale.

        Le jeu repond parfois avec un code d'erreur tout en fournissant un corps
        JSON utile : hors session, GetGameState renvoie 503 avec l'etat courant.
        On distingue donc "le jeu a repondu" (meme en erreur) de "le jeu est
        ferme" (connexion refusee).
        """
        url = f"{self.base}/{path.lstrip('/')}"
        req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body, status = resp.read().decode("utf-8", "replace"), resp.status
        except urllib.error.HTTPError as exc:
            # HTTPError derive de URLError : a intercepter en premier.
            body, status = exc.read().decode("utf-8", "replace"), exc.code
        except urllib.error.URLError as exc:
            raise GameNotRunningError(str(getattr(exc, "reason", exc)), port=self.port) from exc

        if raw:
            return body
        if body.strip():
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                pass
        if status >= 400:
            raise HubError(f"{path} : le jeu a repondu HTTP {status}")
        return None

    def is_running(self):
        """True des lors que le jeu repond, meme par un code d'erreur."""
        try:
            self.get("rest/sessions/GetGameState")
        except GameNotRunningError:
            return False
        except HubError:
            pass
        return True

    def auth_session_ticket(self):
        """Ticket de session Steam, necessaire pour s'authentifier aupres de raceos.gg."""
        payload = self.get("rest/profile/getAuthSessionTicket")
        ticket = (payload or {}).get("authSessionTicket")
        if not ticket:
            raise GameNotRunningError("le jeu n'a pas renvoye de ticket Steam", port=self.port)
        return ticket

    def game_state(self):
        """Etat courant : {'status', 'reason', 'gameState'}."""
        return self.get("rest/sessions/GetGameState") or {}

    # --- utile pour les modules a venir (overlays, strategie) ---

    def tireinfo(self):
        """Temperatures et pressions des pneus, telles que le jeu les affiche.

        Trois sondes par pneu — gauche, centre, droite — en Kelvin, et la
        pression en kPa.

        **Valeurs de reglage, pas de course** : en piste, l'endpoint continue
        de rendre celles du garage. Mesure — trois lectures a deux secondes
        donnent 75,50 °C et 131,000 kPa a l'identique pendant que la voiture
        roule. Il renseigne donc sur un setup, jamais sur un tour.
        """
        return self.get("rest/garage/tireinfo")

    def standings(self):
        return self.get("rest/watch/standings")

    def weather(self):
        return self.get("rest/sessions/weather")

    def swagger_schema(self):
        """Schema OpenAPI complet des 179 endpoints locaux."""
        return self.get("swagger-schema.json")
