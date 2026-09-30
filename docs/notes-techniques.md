# LMU Central — notes techniques

> Le detail du fonctionnement interne : ce que publie le jeu, ce qu'il ne
> publie pas, et les pieges releves en le mesurant. Pour l'usage courant, voir
> le [README](../README.md).


Application Windows pour Le Mans Ultimate, concue pour accueillir plusieurs
modules. Premier module livre : **DR / SR exacts**.

## Lancer

```
dist/LMU Central.exe
```

Executable autonome : ni Python ni dependance requis sur la machine.

Pendant le developpement :

```bash
py -3 app.py      # interface graphique
py -3 hub.py      # version ligne de commande
```

## Reconstruire l'executable

```bash
py -3 build.py
```

Produit `dist/LMU Central.exe` (~35 Mo, demarrage ~1,4 s).

> **Piege a connaitre** : modules et pages sont decouverts dynamiquement par
> `pkgutil`. Aucun import statique ne les mentionne, donc PyInstaller ne les
> embarque pas tout seul et l'application demarre **vide**. L'option
> `--collect-submodules lmu_central` dans `build.py` regle ca — ne pas la retirer
> en ajoutant de nouveaux modules.

## Modules

| Module | Etat | Description |
|---|---|---|
| `ratings` | actif | DR / SR au centieme de pourcent, amis Steam, historique complet des courses |
| `calendrier` | actif | epreuves a venir, et amis inscrits dessus |
| `setups` | actif | consulter et comparer ses setups, jeu ferme |
| `remap` | actif | molettes crantees du volant : une position par frappe, avec overlay en jeu |
| `overlays` | a venir | overlays de telemetrie en direct, personnalisables |

## Architecture

```
app.py                     lance l'interface graphique
hub.py                     lance la version ligne de commande
build.py                   construit dist/LMU Central.exe
make_icon.py               genere assets/icon.ico
lmu_central/
  core/                    logique metier, partagee par les deux interfaces
    cache.py               session (30 min), dernieres valeurs, courses gardees
    errors.py              exceptions affichables
    localapi.py            API REST locale du jeu (127.0.0.1:6397)
    raceos.py              backend en ligne raceos.gg (lecture seule)
    courses.py             dernieres courses publiees par le backend
    calendrier.py          epreuves a venir + amis inscrits
    setups.py              lecture et comparaison des fichiers .svm
    installation.py        ou le jeu est installe (bibliotheques Steam)
    explorateur.py         montre un fichier dans l'Explorateur Windows
    historique.py          releves locaux : le pourcentage exact au fil du temps
    ratings.py             chargement des ratings + repli hors ligne
    timefmt.py             horodatages en heure locale
  gui/                     interface graphique (CustomTkinter)
    app.py                 fenetre, barre laterale, barre d'etat
    theme.py               palette et polices
    widgets.py             cartes de rating, lignes d'amis
    pages/                 une page par fonctionnalite
      base.py              classe Page
      ratings.py           page DR / SR, amis et historique
      calendrier.py        page des epreuves a venir
      setups.py            page des setups : liste, valeurs, comparaison
    vues.py                les deux vues commutables (amis / courses)
  remap/                   remap des molettes (repris du projet autonome)
    panneau.py             l'interface, integrable dans une fenetre hote
    moteur.py              lecture du volant, envoi des raccourcis, overlay
    config.py              configuration, avec reprise de l'ancienne
    theme.py               palette de l'overlay en jeu
  ui/console.py            rendu terminal
  modules/                 une commande par fonctionnalite
    base.py                classe Module + Context partage
    ratings.py             commande DR / SR
```

Les deux interfaces partagent `core/` : la logique n'existe qu'une fois.

**Ajouter une page graphique** : deposer un fichier dans `lmu_central/gui/pages/`
avec une sous-classe de `Page`. Elle apparait toute seule dans la barre
laterale.

```python
from .base import Page

class MaPage(Page):
    name = "exemple"
    title = "Exemple"
    order = 20

    def build(self):
        ...          # construit l'interface une seule fois

    def on_show(self):
        ...          # appele a chaque affichage

    # self.ctx.local / self.ctx.raceos : acces aux donnees
    # self.app.run_async(work, on_done) : reseau sans figer l'interface
```

**Ajouter une fonctionnalite** : deposer un fichier dans `lmu_central/modules/`
avec une sous-classe de `Module`. Elle est detectee et branchee sur la ligne
de commande automatiquement, sans toucher au reste.

```python
from .base import Module

class MonModule(Module):
    name = "exemple"
    description = "Ce que fait le module"

    def add_arguments(self, parser):
        parser.add_argument("--option")

    def run(self, args, ctx):
        ctx.local    # API locale du jeu
        ctx.raceos   # backend en ligne, deja authentifie
        return 0
```

`Context` mutualise les ressources : l'authentification RaceOS n'a lieu qu'une
fois par execution, meme si plusieurs modules la reclament.

## DR / SR : comment ca marche

Le jeu n'affiche la progression que par tranches de 10 %. Le serveur, lui,
renvoie la valeur exacte — le jeu choisit simplement de ne pas l'afficher.

Chaine reconstituee depuis l'interface web du jeu (`Bin/UI.zip`, non minifiee) :

1. `GET http://127.0.0.1:6397/rest/profile/getAuthSessionTicket` — ticket Steam
2. `POST https://raceos.gg/authenticate` avec `{token, game:"lmu", platform:"steam"}`
   → `accessToken` + **le profil complet, ratings inclus**
3. RPC suivants avec l'en-tete `Game-Authorization: Bearer <accessToken>`

| Champ | Contenu |
|---|---|
| `driverRank.elo` | valeur DR brute (ex. 2510.29) |
| `driverRank.progress` | progression exacte dans le tier, en % |
| `safetyRank.rating` | valeur SR brute |
| `safetyRank.progress` | progression exacte dans le tier, en % |
| `safetyRank.contactImpactsPerLapRatio` | contacts par tour, + historique 10 courses |

## Faut-il que le jeu soit ouvert ?

Pas toujours. Le hub gere trois situations :

| Situation | Ratings | Historique des courses | Calendrier |
|---|---|---|---|
| Jeu ouvert | valeurs fraiches | chargement depuis le backend | complet, amis compris |
| Jeu ferme, session de moins de 30 min | **fraiches quand meme** | **depuis le backend quand meme** | complet, amis compris |
| Jeu ferme, session expiree | dernieres valeurs connues, datees | dernieres courses connues, datees | horaires exacts, sans les amis |

L'onglet **Setups** ne figure pas dans ce tableau : il ne parle a personne. Les
setups sont des fichiers sur le disque, il les lit directement, et le jeu peut
rester ferme indefiniment.

Seule la **premiere** authentification exige le jeu : lui seul peut produire un
ticket Steam. L'accessToken obtenu reste ensuite valable **30 minutes**, et le
hub le reutilise sans le jeu.

Passe ce delai, il faut relancer LMU : le backend n'expose **aucun mecanisme de
renouvellement** (pas de refresh token cote RaceOS), le ticket Steam est donc
l'unique porte d'entree.

```bash
py -3 hub.py                   # affiche le temps restant sur la session
py -3 hub.py ratings --refresh # force une reauthentification (jeu requis)
```

## Historique des courses

Le bas de la page Ratings bascule entre deux vues, par un selecteur :

- **Amis Steam** — leurs rangs et leurs statistiques ;
- **Historique** — les courses, chargees **20 par 20**.

Colonnes : date, epreuve, circuit, position (avec les places gagnees depuis
la grille), **Driver Rating** et **Safety Rating** — les deux au centieme de
pourcent des que l'historique local couvre la course, chevrons seuls sinon.

Quatre filtres combinables : **epreuve**, **circuit**, **classe** et
**resultat** (victoires, podiums, hors podium, abandons), plus un bouton de
remise a zero. Le resume indique le nombre retenu, la periode couverte et
combien de courses ont leurs pourcentages exacts.

### Chargement incremental

Tirer les 232 courses d'un coup demandait cinq allers-retours et figeait la vue
cinq secondes. Le chargement se fait desormais page par page :

| | Avant | Maintenant |
|---|---|---|
| Premier affichage | ~5 s, 232 courses | **~1 s, 20 courses** |
| Bouton | affichait 60 deja chargees | charge et affiche 20 de plus (~1 s) |

Une page du backend vaut exactement un bloc affiche : un clic, un aller-retour
par type d'epreuve encore ouvert. Quand un filtre restrictif ecarte tout ce qui
arrive, un seul clic tire jusqu'a trois pages plutot que de sembler ne rien
faire — avec le filtre « Abandons », les clics successifs donnent 1, 5, 10, 24
puis 30 resultats.

### Deux pieges sur `eventType`, qui cachaient toutes les epreuves speciales

`GET api/v1/results` prend un `eventType`, et le hub en interrogeait trois :
`daily`, `special`, `championship`. Seul le premier existe.

**Le nom.** Les epreuves speciales et les hebdomadaires ne s'appellent pas
`special` mais **`specialevent`** — un seul type pour les deux familles, que
seul le champ `tier` distingue ensuite (`special` ou `weekly`). Mesure :

    eventType=special       -> null
    eventType=specialevent  -> 19 courses
    eventType=zzbogus       -> null

Le backend repond `null` a un type inconnu **exactement** comme a un type
valide dont la page est vide : rien dans la reponse ne signale l'erreur, et
c'est pourquoi elle a tenu si longtemps. Le seul moyen de trancher est de
connaitre la bonne valeur par ailleurs — ici, le champ `type` que
`special-events/{famille}` porte sur chaque serie.

**L'ordre.** Les types etaient parcourus l'un apres l'autre : toutes les
courses quotidiennes d'abord — jusqu'a mille, soit cinquante clics — puis
seulement les suivantes. Meme avec le bon nom, une epreuve speciale disputee la
veille serait restee invisible. Ils avancent desormais **de front**, une page de
chacun par tour, puis tri par date.

Effet mesure sur un historique reel : les 19 epreuves speciales et
hebdomadaires apparaissent des le premier tour, la plus recente en tete du
tableau. Aucune n'avait jamais ete affichee.

Le bouton dit ce qu'il va faire : « Afficher 20 de plus » quand les courses
sont deja en memoire, « Charger les courses suivantes » quand il faut les
demander au serveur. Il disparait une fois tout charge.

### Hors ligne

Les courses disputees ne changent plus : les garder est sans risque, et c'est
ce qui evite un onglet vide des que la session a expire. Chaque page chargee
est ecrite dans `courses.json` — environ 100 Ko pour 232 courses, la forme
reduite aux seuls champs affiches plutot que les reponses brutes du backend.

Backend injoignable, la vue repart de ce cache : memes filtres, meme tableau,
et **les pourcentages exacts sont recalcules quand meme** puisqu'ils viennent
de l'historique local. Le resume le signale : *« Hors ligne — dernier
chargement du 18/09/2026 a 23h31 »*.

Le cache fusionne au lieu de s'ecraser : une session ou l'on ne deroule que la
premiere page ne rabougrit pas un cache qui contenait tout l'historique.

Si aucune course n'a jamais ete chargee, la vue le dit et explique quoi faire,
plutot que de rester blanche.

### Le pourcentage exact par course

Le backend ne publie **nulle part** le pourcentage gagne ou perdu sur une
course. `GET api/v1/results` fournit `driverRankAdjustment`, un entier de -3 a
+3 que le jeu affiche sous forme de chevrons : une direction, pas une valeur.
Et sur cet endpoint comme sur les autres, `elo` vaut 0 et `progress` est arrondi
a la dizaine.

Le hub le reconstruit donc lui-meme :

1. chaque chargement des ratings releve l'ELO exact (seule `/authenticate` le
   donne) dans `historique-ratings.json` ;
2. un releve n'est ajoute que si le DR **ou** le SR a bouge — une course,
   donc ; les deux comptent, une course propre peut ne rien changer au DR et
   faire monter le SR ;
3. l'ecart entre deux releves consecutifs est le gain ou la perte reelle ;
4. les courses de `api/v1/results` tombant dans l'intervalle de deux releves se
   voient attribuer cet ecart.

Le calcul tient compte des changements de tier : passer de Silver 3 a 95 % a
Gold 1 a 10 % est un gain de 15 points, pas une chute de 85.

Quand plusieurs courses tombent entre deux releves, l'ecart les concerne toutes
ensemble : il est affiche en gris avec la mention « (N×) » plutot que reparti au
hasard.

### Releve automatique en fin de course

Pour que chaque course ait sa valeur propre, il faut un releve **entre** deux
courses. Le hub s'en charge tant qu'il est ouvert :

- il interroge l'API locale du jeu toutes les 15 s ;
- `status` passe de disponible a `unavailable` quand on quitte une session :
  c'est la fin d'une course ;
- un releve est alors tente a +45 s, +2 min et +5 min — le backend met un
  instant a publier le nouveau rating — puis toutes les 5 min pendant deux
  heures, et s'arrete des qu'une valeur differente apparait ;
- la page Historique se rafraichit toute seule si elle est ouverte.

**Pourquoi les tentatives tardives.** Relever le rating passe par
`/authenticate`, qui reclame un ticket Steam : seul le jeu **en cours
d'execution** peut le fournir. Un joueur qui ferme LMU en sortant de sa course
n'a donc rien de relevable, et s'arreter a +5 min perdrait le pourcentage de
cette course pour de bon. Les tentatives lentes rattrapent le cas ou le jeu
est relance plus tard : la valeur lue est toujours la bonne, seule sa date
glisse. La barre d'etat le dit au lieu d'echouer en silence.

Laisse le hub ouvert pendant que tu joues — et, apres ta derniere course,
laisse le jeu tourner une minute de plus.

**Consequence a assumer** : l'historique demarre au premier lancement du hub.
Les courses anterieures n'affichent que les chevrons — leur pourcentage exact
n'existe nulle part et n'est pas reconstituable.

## Limite connue : la precision n'existe qu'a l'authentification

Ce n'est pas une censure "moi contre les autres", comme on pourrait le croire :
c'est **l'endpoint** qui determine le niveau de detail.

| Endpoint | `elo` / `rating` | `progress` |
|---|---|---|
| `POST /authenticate` | **valeur exacte** | **exact au centieme** |
| `POST api/v1/player/friends-list` | `0` | arrondi a 10 % |
| `POST api/v1/players` | `0` | arrondi a 10 % |
| `GET api/v1/results` | `0` | arrondi a 10 % |
| `GET api/v1/player` | ignore l'identifiant passe, renvoie le profil connecte | |

Verifie : dans `api/v1/results`, **meme sa propre entree** ressort avec
`elo: 0` et un `progress` arrondi, alors que `/authenticate` renvoie
`86.76229` au meme instant. La troncature est donc appliquee partout sauf a
l'authentification.

Or `/authenticate` ne renvoie qu'une chose : le profil du **porteur du ticket
Steam**. Et seul le jeu, lance sur le compte concerne, peut produire ce ticket.

Deuxieme consequence, sur son propre profil cette fois : le profil rendu par
`RaceOS.authenticate()` sans `force` est celui du dernier relevé, fige pour
les 30 minutes du jeton. Une course disputee entre-temps ne s'y voit pas,
alors que les amis, les statistiques et les courses, eux, sont relus a chaque
appel. Le bouton *Actualiser* force donc une vraie reauthentification ; quand
le jeu est ferme, elle echoue et la page affiche la date du profil plutot que
de faire passer une valeur perimee pour fraiche.

**Consequence** : obtenir le pourcentage exact de quelqu'un d'autre est
impossible, quel que soit l'outil. Fournir un pseudo ou un SteamID ne change
rien — l'autorisation vient du ticket, jamais de l'identifiant demande.

Seule voie possible : l'interesse lance `py -3 hub.py ratings --json` sur son
propre PC et partage le resultat.

## Module Macros Volant

Reprise de l'application autonome qui portait le nom *Remap Volant*, integree telle quelle : meme
interface, memes reglages.

Une molette crantee est un **encodeur relatif** — elle n'envoie que deux
impulsions (monte / descend), jamais sa position absolue. Sans ce module,
chaque cran traverse declenche son action au passage. Ici le programme compte
les impulsions et garde la position en memoire : tourner ne fait rien, seul le
bouton de confirmation declenche l'action de la position courante.

### Administrateur : seulement pour Le Mans Ultimate

Le hub demarre normalement, **sans elevation ni invite UAC**.

Windows interdit a un processus non-eleve d'injecter des frappes vers un
processus **eleve**. L'elevation n'est donc utile que selon la cible :

| Application visee | Elevation requise ? |
|---|---|
| Voicemod, Discord, OBS (processus normaux) | non — fonctionne tel quel |
| Le Mans Ultimate (lance par EasyAntiCheat) | oui |

Quand c'est LMU qui est vise : clic droit sur `LMU Central.exe` > *Executer en tant
qu'administrateur*. La page Macros Volant rappelle ce point si le hub n'est pas
eleve, sans rien bloquer.

### Configuration

Elle vit avec celle du hub : `.cache/remap-molettes.json` en developpement,
`%LOCALAPPDATA%\LMU Central\` une fois empaquete.

> L'application s'appelait auparavant **LMU Hub**. Au premier lancement sous le
> nouveau nom, le cache de l'ancien dossier est **fusionne** dans le nouveau :
> les releves de rating des deux sont reunis et dedoublonnes par date, les
> autres fichiers repris s'ils sont plus recents. Rien n'est supprime —
> l'ancien dossier est simplement renomme `LMU Hub (repris)`. Une fusion, et
> non un renommage, parce que les deux dossiers peuvent coexister : c'est
> justement le cas ou un renommage abandonnerait les releves les plus recents,
> et un releve perdu est un pourcentage de course perdu pour de bon.

Au premier lancement sur une machine, il n'y a rien a reprendre et c'est
voulu : les molettes partent vides, et le bouton **Detecter** apprend les
boutons de ce volant-la. Aucune configuration n'est livree avec le programme —
voir plus bas pourquoi.

### Le filet de securite

`%LOCALAPPDATA%` **depend du compte Windows qui execute le programme**. Lance en
administrateur sous un autre compte que le sien — ce que l'elevation demande
quand le compte courant n'est pas administrateur — l'application cherche sa
configuration dans un profil ou elle n'a jamais rien ecrit, n'y trouve rien, et
repart des valeurs d'usine. Vu de l'ecran, tous les raccourcis ont disparu.

Une copie de secours existe pour ce cas. Elle est cherchee **a cote de
l'executable**, et nulle part ailleurs :

    <dossier de l'exe>/sauvegardes/  la copie entretenue (voir plus bas)
    <dossier parent de l'exe>/       idem, pour un exe range dans dist/

Ces deux emplacements ont une propriete essentielle : **c'est l'application
qui les ecrit, sur la machine de celui qui s'en sert**. Ils ne peuvent donc
contenir que ses reglages a lui. En developpement la liste est vide — la
configuration vit dans `.cache/`, et il n'y a pas de second profil Windows
dont il faudrait se proteger.

**Ce qu'on ne fait pas : livrer une configuration avec le programme.** Ni
embarquee dans le `.exe`, ni posee dans le depot, ni cherchee a un chemin que
le developpeur serait seul a connaitre. Une configuration livree est celle de
qui a compile, et elle s'installe toute seule au premier lancement chez tout
le monde. Mesure sur une machine vierge simulee, a l'epoque ou elle etait
embarquee : douze macros personnelles et les numeros de boutons d'un volant
Fanatec precis, poses dans le profil d'un inconnu dont le volant n'a pas les
memes — des molettes qui ont l'air reglees et qui ne font rien.

La regle tient en une phrase : **le filet rattrape une configuration perdue,
il n'en invente jamais une**. `build.py` n'embarque donc que `assets/`, et le
depot ne contient aucun reglage.

Corollaire pour la distribution : on envoie **`LMU Central.exe` seul**. Un
dossier `sauvegardes/` pose a cote d'un exe est la copie de son proprietaire —
le filet voulu chez lui, une fuite chez les autres.

Deux garde-fous encadrent la reprise :

- elle remplace aussi un fichier **deja ecrit avec les valeurs d'usine** — sinon
  une seule session malheureuse figerait la perte sur le disque ;
- elle ne touche **jamais** une configuration ou quoi que ce soit a ete regle,
  meme si tous les raccourcis en ont ete effaces. Un fichier n'est repris que
  s'il est identique, molette pour molette, a la sortie d'usine.

Quand il ne reste vraiment rien, la page **le dit** au lieu de presenter des
molettes vides : le silence se lit comme une panne.

**La copie ne reste pas figee.** Une copie datant d'un jour precis ne sauve
qu'une fois, et rendrait ensuite des raccourcis perimes. Chaque demarrage et
chaque enregistrement en reecrivent donc une a cote de l'executable
(`<dossier de l'exe>/sauvegardes/remap-config-origine.json`) — le seul endroit
qui ne depende pas du compte Windows. Au demarrage aussi, sinon il n'y aurait
aucun filet tant que l'utilisateur ne touche a rien. Une reserve : jamais avec
les valeurs d'usine, qui effaceraient une copie valable. Si le dossier est en
lecture seule — un exe range dans `Program Files` —, l'echec est silencieux,
et l'utilisateur repart simplement des valeurs d'usine.

### Notes d'integration

- `Application(tk.Tk)` est devenue `PanneauRemap(ctk.CTkFrame)` : la fenetre est
  fournie par le hub, le panneau ne gere plus ni titre, ni icone, ni fermeture.
- **La couche d'affichage a ete reecrite en CustomTkinter**, avec la palette du
  hub (`lmu_central/gui/theme.py`) et ses cartes (`lmu_central/gui/widgets.py`). Le
  theme ttk et les widgets dessines a la main du projet d'origine ont disparu ;
  `remap/theme.py` ne sert plus qu'a l'overlay en jeu, qui garde son style.
- **Toute la logique est inchangee** : moteur, capture de raccourcis, detection
  des boutons, envoi, overlay. Seul le contrat avec les widgets a ete adapte
  (`foreground=` devient `text_color=` pour les labels CustomTkinter).
- **Les 12 positions sont sur deux colonnes de six**, et passent sur une seule
  colonne sous 830 px de large. C'est la page la plus dense du hub, d'ou la
  fenetre par defaut de 1120x860.
- Le panneau est construit **a la premiere ouverture** de la page : pygame met
  un instant a demarrer, inutile de ralentir le lancement du hub.
- `Page.on_close()` permet a une page de liberer ses ressources ; le hub
  l'appelle sur chaque page avant de quitter (ici : volant, overlay, clavier).
- Les raccourcis s'affichent en **Cascadia Mono 13** : elle distingue nettement
  `l` et `1`, `O` et `0`, ce qui compte pour relire une combinaison d'un coup
  d'oeil. `theme.mono_family()` choisit la meilleure police installee et retombe
  sur Consolas puis Lucida Console si besoin.

## Calendrier et amis

L'onglet montre les epreuves a venir et, pour chacune, les amis inscrits.

### Les cinq appels, verifies contre le backend

    GET  api/v1/daily/schedule
        La rotation de la semaine : trois niveaux (beginner, intermediate,
        advanced), trois series chacun, avec circuit, voitures, duree et les
        horaires de depart de la journee. **Un seul appel porte tout le
        calendrier quotidien.**

    GET  api/v1/daily/list/{niveau}?take={n}
        Les occurrences concretes : identifiant, statut, horaire.

    GET  api/v1/special-events/{famille}
        Les hebdomadaires (`weekly`) et les epreuves speciales (`special`).

    POST api/v1/event/overview  {game, eventType, eventId}
        Le detail d'une occurrence : nombre d'inscrits, splits, et `friends`.

    GET  api/v1/event/entries/{type}/{id}?page={p}&take={n}
        Les engages, seule source des amis une fois l'epreuve lancee.

### Hebdomadaires et epreuves speciales

`daily/schedule` ne porte **que** la rotation quotidienne. Les « WEC Weekly »
et les « ELMS 4 Hours of Silverstone » n'y figurent nulle part : elles viennent
de `api/v1/special-events/{famille}`, un appel par famille.

La route ne s'annonce pas. Elle a ete trouvee dans les traces du jeu, ou elle
n'apparait que parce qu'un appel avait echoue :

    OnHTTPResourceRequest failed for method: GET,
    URL: https://raceos.gg/api/v1/special-events/special with status 500

Cet appel-la porte **tout** : la serie et ses occurrences datees, dans
`events`, chacune avec son identifiant et son nombre d'inscrits. Contrairement
au quotidien, aucun rapprochement avec une seconde liste n'est necessaire, et
les inscrits sont connus sans passer par `event/overview`.

Deux details qui ne se devinent pas :

- les deux familles partagent le meme `type` — `specialevent` — et seul
  `tier.name` les separe ; c'est ce nom-la que le hub prend pour niveau, ce qui
  donne les filtres « Hebdo » et « Speciale » ;
- une epreuve speciale enchaine essais, qualification et course. Sa duree est
  leur **somme**, temps d'attente compris : 265 min pour une 4 heures. Prendre
  la seule duree de course la declarerait terminee alors qu'elle roule encore.

L'enrichissement par `event/overview` a un quota **par type d'epreuve**, non
global. Les quotidiennes partant toutes les dix minutes, les plus proches sont
forcement quotidiennes : un quota global condamnait les epreuves speciales a ne
jamais montrer leurs amis inscrits — justement celles qu'on prepare a l'avance.

Hors ligne, elles ne se rejouent pas comme la rotation : leurs departs sont
dates une fois pour toutes. Le cache les sert donc exactement, mais la liste se
vide a mesure qu'elles passent au lieu de se prolonger. Le resume garde les
departs, le circuit et les durees, et laisse tomber reglages serveur, meteo
minute par minute et livrees — 10 Ko au lieu de plusieurs centaines.

> **Deux pieges** que seule la mesure a reveles. `daily/list` prend le
> **niveau**, pas le type d'epreuve : `daily/list/daily` renvoie une liste
> vide, `daily/list/beginner` renvoie les epreuves. Et le champ `friends` est
> **absent** de `daily/list` : il n'apparait que dans `event/overview`. La
> classe `Event` du bundle du jeu le declare pourtant, mais comme valeur par
> defaut — lire le code ne suffisait pas, il fallait appeler.

Le detail coute un aller-retour par epreuve : on le reserve aux huit
prochaines, les seules ou l'inscription d'un ami a un interet.

### Les amis en course

Premiere version : un ami inscrit disparaissait de l'onglet **au moment meme
ou il prenait la piste**. Mesure du 30 septembre 2026, sur une quotidienne
intermediaire (sessions a 10:50, course a 11:03) :

| Heure | `daily/list` | `event/overview` |
|---|---|---|
| 10:48 | listee, `ServersRunning` | `friends` servi |
| 10:51 | **absente** | `Running`, `friends: []` — inscrits toujours donnes |

Une epreuve quitte les listes des qu'elle passe en `Running`, c'est-a-dire aux
essais, un quart d'heure avant le depart. Le hub perdait alors son identifiant
et ne demandait plus rien. Les epreuves speciales font pire : l'occurrence
lancee sort de `special-events`, et l'epreuve entiere quittait le calendrier —
six heures durant pour les 6 Heures de Fuji.

Le jeu lui-meme n'affiche les amis inscrits qu'avant le depart ; ensuite un
drapeau a damier les remplace.

La parade tient en deux morceaux :

- **une memoire locale** (`occurrences.json` dans le cache) : chaque epreuve vue
  avant son depart y est retenue, identifiant compris, jusqu'a sa fin. Une fois
  lancee, on la retrouve la ; une speciale y est meme reconstruite entiere ;
- **`GET api/v1/event/entries/{type}/{id}?page={p}&take={n}`**, trouvee dans le
  bundle du jeu (`Bin/UI.zip`). Les engages y restent servis pendant la course,
  avec nom et avatar Steam mais **sans identifiant de joueur**. On les croise
  avec `friends-list` par l'empreinte de l'avatar (40 caracteres hexadecimaux,
  la meme en `_medium` et `_full`), a defaut par le nom. Les equipiers
  (`teamMembers`) comptent aussi. `page` commence a **1** : `page=0` renvoie la
  meme chose que `page=1`, ce qui double silencieusement les engages.

Limite assumee : une epreuve deja lancee au premier lancement du hub n'a jamais
ete vue, et reste introuvable — aucune route ne liste les epreuves en cours.

### Pourquoi `daily/schedule` porte le calendrier

Ses horaires couvrent exactement vingt-quatre heures et se repetent a
l'identique chaque jour de la semaine. Mis en cache, le calendrier se
reconstruit donc **jeu ferme**, sans perte de precision : verifie en comparant
les 440 horaires calcules depuis le cache a ceux obtenus en direct — identiques.

C'est ce que font les sites du genre de lmuschedule.com, a ceci pres qu'ils
recopient la rotation a la main (leur page affiche « Week Of », et un fichier
`updated-date.txt` porte la date de mise a jour). Le hub la prend a la source.

Seuls les **inscrits et les amis** manquent hors ligne : donnees vivantes et
personnelles, derriere un jeton de 30 minutes qu'on n'obtient que par un ticket
Steam. L'interface distingue alors « aucun ami inscrit » de « je ne peux pas
savoir », plutot que d'afficher un vide ambigu.

### Ce qui n'est pas possible

**La presence en direct n'existe pas.** Savoir qu'un ami est en solo, en essais
libres ou dans les menus n'est publie nulle part :

- aucun endpoint REST ne donne un etat de connexion pour autrui — `isOnline`,
  dans l'interface du jeu, ne concerne que **ta** connexion a RaceOS et Steam ;
- aucune API de presence Nakama n'est utilisee par le jeu (`followUsers`,
  `status_follow` : zero occurrence dans son bundle) ;
- `friends-list` ne renvoie ni statut ni derniere activite exploitable.

Rien n'est non plus accessible **sans jeton** : les endpoints du calendrier
repondent tous 401, seul `api/v1/maintenance` est public.

### Affichage

Deux jours de rotation font plus de 400 epreuves, soit des milliers de widgets.
Le tableau en dessine **25 a la fois** (~0,8 s), avec un bouton pour la suite,
comme l'historique des courses.

## Setups

L'onglet liste les setups enregistres sur le disque, en montre les valeurs et
en compare deux. **Le jeu n'a pas besoin d'etre lance** : tout est lu dans

    <installation>/UserData/player/Settings/<circuit>/<nom>.svm

L'installation est trouvee par le registre puis par `libraryfolders.vdf`, donc
sans supposer que Steam est sur `C:`. En dernier recours, la variable
d'environnement `LMU_CENTRAL_JEU` impose le chemin.

### Le format

Un `.svm` est un fichier texte. Chaque ligne y porte deux choses :

    RWSetting=6//4.50 deg
             ^   ^
             |   ce que le jeu affiche dans son garage
             l'indice interne

**L'indice ne veut rien dire hors de sa voiture** : le cran 6 vaut 4,50 deg sur
une GT3 et tout autre chose sur une hypercar. C'est donc le texte affiche qui
sert de valeur, ici comme a la comparaison.

### Trois pieges, releves sur les 444 setups du disque

**Le texte est traduit dans la langue du jeu au moment de l'enregistrement.**
Un meme reglage s'ecrit `Off`, `Non`, `Aus` ou `Disattivato` selon la machine
d'ou vient le setup ; l'antipatinage se dit `Available`, `Disponible`,
`Disponibile` ou `Verfugbar` ; les degres s'ecrivent `deg` ou `Grad`, les tours
`laps` ou `Runden`. Compares tels quels, deux setups identiques sembleraient
differer partout. `normaliser` ramene le tout au francais du jeu.

La table de traduction ne contient que ce que le corpus prouve traduit. Les
noms propres — `Standard`, `Sprint`, `Le Mans`, `Short`, `High Speed`, `RWD`,
`Full` — restent tels quels : les traduire serait inventer.

> Un piege dans le piege : le jeu emploie le **meme adjectif** pour une gomme
> et pour un amortisseur. `100% Soft` est un pneu tendre, `0 (soft)` un
> amortisseur souple, et sa traduction francaise officielle dit `0 (tendre)`.
> Une premiere version traduisait les deux differemment et fabriquait des
> ecarts la ou il n'y en avait pas.

**Ce que la voiture n'a pas s'ecrit de trois facons.** `N/A`, `N/D` et `N/V`
sont le meme vide, en trois langues. Sur les 167 cles rencontrees, une bonne
moitie ne concerne jamais la voiture qu'on regarde : ces lignes-la sont
ecartees, sinon le tableau noierait les reglages reels.

**Deux fichiers sur 444 sont en cp1252, pas en UTF-8.** Lus sans precaution,
leur angle de braquage devient `516? (19.7?)` au lieu de `516° (19.7°)`.

### Ce qui n'est pas un reglage

Certaines valeurs decrivent un etat, pas un choix, et fausseraient la
comparaison :

| Valeur | Pourquoi elle est ignoree a la comparaison |
|---|---|
| `100% (32.3 tours)` | l'autonomie estimee depend du circuit, pas du reglage |
| `94% Medium` | l'usure du train au moment de l'enregistrement |

La deuxieme a une consequence visible : sans elle, trente setups passaient pour
**asymetriques** parce qu'un pneu etait use a 94 % a gauche et a 96 % a droite.
Une fois l'usure mise de cote, les 444 setups du disque sont symetriques, et le
tableau des roues tient en deux colonnes — avant, arriere — au lieu de quatre.
Les quatre colonnes restent la pour un setup qui, lui, serait vraiment
dissymetrique.

`FuelSetting` est aussi laisse de cote : il redit `FuelCapacitySetting`, la
meme charge divisee par cent (`0.88` pour `88.0L`) sur les voitures qui se
remplissent en litres, et bloquee a `1.00` sur celles qui se remplissent en
energie virtuelle. La ligne « Carburant » suffit, et elle porte en plus
l'estimation en tours.

### Lire et comparer

Le panneau de gauche filtre par **circuit**, par **voiture**, par **categorie**
et par texte libre. Les valeurs sont classees par ordre alphabetique, avec leur
compte a cote : la question « qu'est-ce que j'ai, et ou » trouve sa reponse sans
ouvrir quoi que ce soit.

Chaque menu ne propose que ce qui reste **atteignable** compte tenu des autres.
Choisir la Genesis laisse une seule categorie — Hypercar — et quatorze circuits
sur dix-neuf. Un menu qui listerait tout finirait par offrir des combinaisons
vides.

**La liste se regroupe selon ce qui est filtre** :

| Filtres actifs | La liste montre |
|---|---|
| un circuit | les **voitures** qui y ont des setups, repliees, avec leur compte |
| une voiture | les **circuits** ou elle en a |
| les deux, ou aucun | les setups, a plat |

Un clic deplie un groupe et decale ses setups sous leur en-tete. La ou le nom
de la voiture et celui du circuit sont deja connus, chaque ligne affiche sa
**date** plutot que de les repeter — c'est elle qui distingue deux versions
d'un meme reglage.

Tant qu'aucun setup n'est ouvert, le panneau de droite recapitule la collection
voiture par voiture.

Le panneau de droite presente les valeurs dans l'ordre du garage du jeu, les
quatre roues cote a cote. Une cle inconnue n'est jamais perdue : elle atterrit
dans « Autres reglages », pour qu'une voiture ajoutee par une mise a jour ne
fasse rien disparaitre en silence.

« Comparer avec… » epingle le setup ouvert ; choisir le suivant bascule le
panneau en comparaison. Seules les lignes qui different sont montrees, et le
resume donne le compte exact (`16 différence(s) sur 92 réglages comparés`).
Chaque nom de setup prend la couleur de sa colonne, sinon rien ne dirait
laquelle des deux valeurs appartient a quel fichier.

**Tout est en lecture seule.** Le hub n'ecrit jamais dans les fichiers du jeu.
« Copier » met le setup — ou la comparaison — dans le presse-papiers, en texte,
pret a coller dans un message.

« Voir dans le dossier » ouvre l'Explorateur avec le fichier du setup **deja
selectionne** (`explorer /select,"<fichier>"`), plutot que le dossier d'un
circuit et ses dizaines de fichiers. En comparaison, c'est le setup choisi
dans la liste, pas l'epingle. Le hub ne fait que regarder : il n'ouvre pas le
fichier et n'y touche pas.

L'Explorateur ne signale aucune de ses erreurs, d'ou deux precautions dans
`core/explorateur.py` :

- le chemin est ramene a des antislashs, la seule forme que `/select` attend ;
- on verifie que le fichier existe. Sinon l'Explorateur ne rouvre pas son
  dossier : il ouvre le **Bureau avec « Documents » surligne**, comme si tout
  s'etait bien passe (constate sous Windows 11). Un setup supprime entre la
  lecture et le clic tomberait dans ce piege ; la barre d'etat dit
  maintenant qu'il n'existe plus.

Ce bouton a aussi fait descendre la note « epingle : … » sous la barre : a
quatre boutons elle ne tenait plus a leur suite, meme a la taille par defaut
(589 px demandes pour 566 offerts). Le debordement existait deja a 720 px
avec un setup epingle, sans que rien ne le mesure.

## Fenetre redimensionnable

Tk ne reorganise rien tout seul : une grille dont les colonnes ont un `minsize`
ne retrecit pas, elle **deborde de son conteneur** et le contenu est coupe sans
avertissement. Une barre de defilement horizontale masquerait le symptome, mais
lire un tableau en le faisant glisser est penible.

Chaque page se replie donc au lieu de se laisser couper. `gui/responsive.py`
fournit trois outils : `suivre_largeur` (rappel debounce sur `<Configure>`),
`suivre_paliers` (ne rappelle qu'au changement de palier, pour ne pas
reconstruire un tableau tous les dix pixels) et `replier_texte` (`wraplength`
suivi sur un ancetre, car un long libelle sans retour a la ligne gonfle sa
carte et pousse ses voisines hors de l'ecran).

| Ce qui se replie | Comment |
|---|---|
| Barre laterale | 210 px, puis 156 px sous 900 px ; logotype sur deux lignes ; menu defilant |
| Cartes DR / SR | cote a cote, puis empilees sous 620 px |
| Filtres de l'historique | 4 colonnes, puis 2, puis 1 |
| Tableau de l'historique | retire circuit, puis epreuve, puis SR ; date, position et DR restent |
| Amis Steam | retire le nombre de courses, puis le SR |
| Calendrier | retire niveau, puis inscrits, puis circuit ; quand, epreuve et amis restent |
| Setups | liste et valeurs cote a cote, puis un panneau a la fois avec un retour |
| Macros Volant | deux colonnes puis une, barre de commandes repliee, page defilante |

Le plancher de la fenetre est descendu de 1040x720 a **720x520**, et rien n'est
coupe a cette taille — verifie a 1400x900, 1120x860, 980x700, 860x620 et
720x520 en comparant, pour chaque compartiment, la place demandee
(`winfo_reqwidth`) a celle recue (`winfo_width`).

## Identite visuelle

Le rouge du hub est celui de la marque : **`#FF1D43`**, releve sur le logo
officiel du jeu (pixel dominant de `logo.png` dans le cache Steam) plutot que
choisi a vue de nez. Il sert d'accent dans l'interface, de couleur des pertes
de rating, et de facade a l'icone.

Le logo reprend la forme livree avec CustomTkinter (MIT, Tom Schimansky) — un
carre arrondi perce, avec son epaisseur en relief — et n'en change que les
couleurs : **rouge en facade, blanc pour le relief**, chacun en degrade,
eclaires depuis le haut a gauche.

`make_icon.py` recolore l'originale pixel par pixel, en reclassant chaque
nuance selon sa luminosite entre les deux bleus d'origine. Recoloration plutot
que redessin : le relief est un decalage subtil, et une forme refaite « a peu
pres » se verrait.

Le degrade du relief descend jusqu'a un gris franc (`#94A3B4`) plutot que de
rester blanc. Teste sur les deux fonds : en blanc pur, sur le fond clair de
l'explorateur de fichiers, le relief disparaissait et il ne restait qu'un « C »
rouge au lieu du carre perce.

Le fichier sert partout : `icon.ico` pour l'executable, la fenetre et la barre
des taches ; `logo.png`, genere en meme temps, pour la marque en tete de la
barre laterale.

> **Piege a connaitre** : l'icone passee a PyInstaller (`--icon`) ne vaut que
> pour le fichier `.exe`, tel que l'explorateur l'affiche. La barre de titre et
> la barre des taches lisent l'icone que **Tk** porte — et CustomTkinter
> installe la sienne, un carre bleu, si personne n'appelle `iconbitmap()`.
> D'ou `App._appliquer_icone()`, et le `--add-data` qui embarque `icon.ico`
> dans l'executable pour qu'elle soit lisible a l'execution.

## Reperes techniques

- API locale auto-documentee : `http://127.0.0.1:6397/swagger/`
  (schema sur `/swagger-schema.json`, **179 endpoints**)
- Hors session, `rest/sessions/GetGameState` repond **HTTP 503** avec un corps
  JSON utile — le client traite ce cas, une erreur HTTP ne signifie pas que le
  jeu est ferme
- Telemetrie temps reel (pour les overlays) : memoire partagee `LMU_Data`
  + evenement `LMU_Data_Event`, SDK officiel fourni dans
  `<install>/Support/SharedMemoryInterface/`

## Attention

`.cache/session.json` contient **ton jeton d'authentification** (30 min de
validite). Il est ignore par git — ne le partage pas. `py -3 hub.py ratings --json`
est la bonne facon de transmettre tes valeurs a quelqu'un : il n'expose que les
ratings, jamais le jeton.

`<install LMU>/coherent_local_storage.json` contient les jetons Nakama **en clair**.
Ne jamais partager ce fichier ni une capture qui le montre.

Tous les appels de ce projet sont en **lecture seule**. Ne pas toucher a
`POST api/v1/player`, qui modifie le profil.
