# LMU Central

Un petit hub pour **Le Mans Ultimate** : tes ratings au centième près, le
calendrier des épreuves, tes setups et les macros de ton volant — le tout dans
une seule fenêtre, à côté du jeu.

## Installation

1. Télécharge l'archive depuis la page **[Releases](https://github.com/MarteauPiqueurdu11/LMU-Central/releases/latest)**.
2. Décompresse-la où tu veux — Documents, bureau, une clé USB.
3. Ouvre le dossier, double-clic sur `LMU Central.exe`.

Rien à installer, rien à configurer. Le hub trouve Le Mans Ultimate tout seul,
même s'il est sur un autre disque que Steam.

> **Windows va râler au premier lancement.** L'exécutable n'est pas signé :
> clique sur *Informations complémentaires* → *Exécuter quand même*.

**Tes données restent dans le dossier.** L'application crée un sous-dossier
`donnees` à côté d'elle : réglages de molettes, historique des ratings, caches.
Déplace le dossier, tout te suit ; sauvegarde-le, tu as tout sauvegardé ; deux
copies sont deux installations indépendantes. Évite seulement `Program Files`,
où Windows interdit l'écriture — le hub retombe alors sur ton profil
utilisateur.

## Les quatre onglets

| Onglet | Ce qu'il fait |
|---|---|
| **Ratings** | Ton DR et ton SR au centième de pourcent — le jeu les arrondit à la dizaine. Les ratings de tes amis Steam, et l'historique de toutes tes courses avec le gain ou la perte exacte de chacune. Et la courbe de ton DR et de ton SR sur 7, 30 ou 90 jours, sur fond de bandes de rang. |
| **Calendrier** | Les épreuves à venir : quotidiennes, hebdomadaires, spéciales et championnats. Avec les amis déjà inscrits, et le compte à rebours avant chaque départ. |
| **Setups** | Tes setups rangés par circuit, avec la valeur de chaque réglage, la comparaison de deux setups côte à côte, et un bouton pour retrouver le fichier dans son dossier. || **Macros Volant** | Transforme les molettes crantées du volant en raccourcis : une position = une frappe. Avec un overlay en jeu pour savoir où tu en es. |

## Faut-il que le jeu soit ouvert ?

Pas forcément.

- **Setups** : jamais. Ce sont des fichiers sur ton disque.
- **Ratings et Calendrier** : le jeu doit être lancé **une fois**, pour
  s'authentifier. Ensuite tu as **30 minutes** où tout marche, jeu fermé.
- Passé ce délai, le hub affiche les dernières valeurs connues, avec leur date.
  Relance LMU pour rafraîchir.

Pourquoi 30 minutes : seul le jeu peut fournir le ticket Steam qui ouvre la
session, et le serveur ne propose aucun moyen de la prolonger.

## Bon à savoir

**Les macros vers le jeu demandent l'administrateur.** Le Mans Ultimate tourne
en mode protégé : pour lui envoyer des touches, le hub doit être lancé en
administrateur (clic droit → *Exécuter en tant qu'administrateur*). Pour
Discord, OBS ou Voicemod, c'est inutile.

**L'historique des ratings démarre au premier lancement.** Le pourcentage exact
gagné ou perdu n'existe nulle part sur les serveurs du jeu : le hub le
reconstruit en relevant ta valeur avant et après chaque course. Tes courses
d'avant n'auront donc que les chevrons du jeu. Laisse le hub ouvert pendant que
tu joues, et le jeu tourner une minute de plus après ta dernière course : le
rating exact ne peut être lu que par le jeu, une fois la course publiée.

**Les molettes partent vides.** Aucune configuration n'est livrée avec le
programme — celle de quelqu'un d'autre viserait des boutons que ton volant n'a
pas. Dans l'onglet *Macros Volant*, clique sur *Détecter* puis actionne le
bouton voulu : il l'apprend.

**Tout est en lecture seule.** Le hub ne modifie jamais ton profil, tes
résultats ni tes fichiers de jeu.

## Ça ne marche pas ?

| Symptôme | Cause |
|---|---|
| « Le Mans Ultimate — fermé » alors qu'il tourne | Le jeu met quelques secondes à ouvrir son serveur local. Attends le menu principal. |
| Ratings vides au premier lancement | Lance le jeu, va jusqu'au menu principal, puis *Actualiser*. |
| Setups introuvables | Le hub n'a pas trouvé l'installation. Définis la variable d'environnement `LMU_CENTRAL_JEU` sur le dossier du jeu. |
| Les macros ne font rien en jeu | Relance le hub en administrateur. |

---

Pour le détail technique — ce que publie l'API du jeu, ce qu'elle ne publie
pas, et les pièges relevés en la mesurant — voir
[docs/notes-techniques.md](docs/notes-techniques.md).

Pour reconstruire l'exécutable depuis les sources :

```bash
py -3 -m pip install -r requirements.txt
py -3 build.py
```
