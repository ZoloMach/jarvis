# Jarvis : assistant personnel vocal pour ton PC

Jarvis t'écoute en permanence, se réveille quand tu commences une phrase par **« Jarvis »** (« Jarvis, ouvre Discord »), te répond à voix haute et agit sur ton ordinateur : ouvrir des applis, voir ton écran, cliquer, taper, lancer tes jeux, enregistrer avec OBS, monter tes vidéos, gérer tes fichiers, régler le son, faire des recherches, programmer des rappels... Et quand il lui manque une capacité, il peut **écrire lui-même un nouvel outil**.

```
 Micro ──► Réveil : son nom en début de phrase (petit Whisper local), « Hey Jarvis » à l'anglaise
           (openWakeWord, local) ou double clap (routine de démarrage)
       ──► Transcription (Whisper, local)
       ──► Cerveau : Claude (ton abonnement, via Claude Code) + ~50 outils pour piloter le PC
       ──► Voix (Edge TTS gratuit, ou ElevenLabs avec ta clé pour une voix plus humaine)
```

Après sa réponse, Jarvis continue d'écouter quelques secondes : tu enchaînes sans redire son nom. Le bouton « Arrêter » le coupe, et « Merci Jarvis » termine la conversation.

Tape **deux fois dans tes mains** : Jarvis lance ta routine de démarrage (applications sur les bons écrans, musique, point du jour). La première fois, il te demande ce qu'elle doit contenir et la note dans `Documents\Jarvis\memoire\routine.md`.

## Installation (Windows 10/11)

1. Télécharge **`Installer-Jarvis.exe`** et double-clique dessus. Si Windows affiche « Windows a protégé votre ordinateur », clique sur **Informations complémentaires** puis **Exécuter quand même** (l'installeur n'est pas signé par un éditeur payant). L'installation télécharge Python et les composants : garde Internet branché quelques minutes.
2. Double-clique sur l'icône **Jarvis** apparue sur ton bureau. La première fois, clique sur **Connecter mon abonnement** : une fenêtre et ton navigateur s'ouvrent, connecte-toi à ton compte Claude (Pro ou Max), puis clique sur « C'est parti ».
3. Dis **« Jarvis »** en début de phrase ou clique sur **Parler**. Tu peux aussi lui écrire en bas de la fenêtre.

Au tout premier lancement, Jarvis télécharge ses modèles de reconnaissance vocale (environ 500 Mo) : il met quelques minutes à être prêt. Les réglages (voix avec bouton « Écouter », intelligence, réveil, mot de passe OBS, lancement au démarrage de Windows) sont dans le bouton **Réglages** de la fenêtre. Pour le désinstaller : Paramètres Windows > Applications > Jarvis.

**Dossier de travail** : Jarvis range son travail dans `Documents\Jarvis` (bouton « Dossier de travail » des Réglages) : `CLAUDE.md` est sa fiche (qui tu es, comment il doit travailler : il la relit à chaque demande et tu peux la modifier), `projets\` reçoit les applications et documents qu'il crée, `memoire\` ses notes, `.claude\skills\` ses compétences (post LinkedIn, point du jour, petite application...). Dis-lui « apprends à... » pour qu'il s'en écrive une nouvelle. Ce dossier sert au mode abonnement (Claude Code).

**Mises à jour** : à chaque lancement, Jarvis regarde s'il existe une nouvelle version sur son dépôt GitHub et l'installe tout seul (une petite fenêtre « Mise à jour de Jarvis » s'affiche quelques secondes). Tes réglages, sa mémoire et les outils qu'il s'est créés sont conservés. Si une nouvelle version ne démarre pas, il revient de lui-même à la précédente. La liste des changements est dans `NOUVEAUTES.md` ; l'interrupteur « Mises à jour automatiques » des Réglages permet de les couper.

Pour le contrôle d'OBS : dans OBS (version 28 ou plus), menu **Outils > Paramètres du serveur WebSocket**, coche « Activer le serveur WebSocket », puis recopie le mot de passe dans les Réglages de Jarvis. Pour les clips de jeu, active aussi le **Replay Buffer** dans Paramètres > Sortie.

### Pour les développeurs

Sans l'installeur : `installer.bat` crée un environnement Python, puis `lancer.bat` démarre Jarvis en console (`--texte`, `--sans-mot-eveil`, `--muet`) ou `lancer.bat --fenetre` ouvre la fenêtre. L'installeur se reconstruit avec `bash installeur/construire.sh` (NSIS 3 requis).

Publier une correction : modifier le code, augmenter le numéro dans `VERSION`, ajouter une section `## <version>` en tête de `NOUVEAUTES.md`, puis pousser sur la branche `main`. Les Jarvis installés la récupèrent à leur prochain lancement (`jarvis/updater.py` : contrôle de `VERSION`, téléchargement de l'archive du dépôt, vérification que le code se lit, nouvelles bibliothèques de `installeur/requirements-windows.txt` installées avec uv, sauvegarde dans `data/version-precedente` et retour arrière automatique si la fenêtre ne démarre pas).

## Ce que tu peux lui demander

**Travailler**
- « Jarvis, ouvre Chrome et cherche les horaires de la Poste. »
- « Lis ce qu'il y a dans mon presse-papiers et résume-le. »
- « Regarde mon écran, c'est quoi cette erreur ? »
- « Range les PDF de mon dossier Téléchargements dans Documents/Factures. »
- « Rappelle-moi dans 25 minutes de faire une pause. »
- « Retiens que mon projet de chaîne s'appelle Zolo Gaming. »

**Jouer**
- « Lance Rocket League. » / « Quels jeux j'ai sur Steam ? »
- « Mode jeu. » (ferme les applis gourmandes listées dans `.env`, ouvre Discord)
- « Mets le son à 40 %. » / « Passe à la musique suivante. »
- « Regarde mon écran : qu'est-ce que je devrais faire dans cette quête ? »

**Enregistrer**
- « Lance l'enregistrement. » / « Mets en pause. » / « Arrête et dis-moi où est le fichier. »
- « Clip ça ! » (sauvegarde les dernières secondes via le Replay Buffer d'OBS)
- « Passe sur la scène Webcam. » / « Coupe mon micro dans OBS. » / « Lance le stream. »

**Monter**
- « Coupe les blancs de ma dernière vidéo dans le dossier Vidéos. » (montage auto des silences)
- « Fais-en une version verticale pour TikTok. »
- « Garde de 1 min 20 à 2 min 05. » / « Accélère-la deux fois. »
- « Ajoute la musique fond.mp3 en fond, assez bas. » / « Compresse-la pour Discord. »
- « Ouvre DaVinci Resolve. »

**Créer**
- « Développe-moi une petite page pour jouer au morpion. » (il la code dans son dossier de travail et l'ouvre)
- « Rédige un post LinkedIn sur ma nouvelle vidéo. » / « Fais-moi le point. »
- « Ouvre Discord sur l'écran du haut. » / « Mets Chrome sur l'autre écran. »
- « Apprends à préparer la description de mes vidéos YouTube. » (nouvelle compétence)

**Tout le reste** : s'il n'a pas d'outil dédié, il passe par PowerShell, ou pilote l'écran (capture, clic, clavier). Si tu lui demandes souvent la même chose : « Jarvis, crée-toi un outil pour ... ». Il écrit un plugin dans `plugins/` qui reste disponible pour toujours.

## Sécurité

Les actions sensibles (commande PowerShell, écriture/déplacement de fichiers, fermer un programme, éteindre le PC, créer un outil) demandent ta **confirmation vocale** : réponds « oui » ou « non ». Tu peux désactiver ça avec `JARVIS_AUTO_CONFIRM=1`, mais c'est déconseillé. Arrêt d'urgence de la souris : envoie le curseur dans le coin en haut à gauche de l'écran.

## Ajouter des capacités à la main

Crée un fichier dans `plugins/` (voir `plugins/exemple_meteo.py`) :

```python
from jarvis.tools import tool

@tool("Ce que fait l'outil, pour que Jarvis sache quand l'utiliser.",
      {"param": {"type": "string", "description": "..."}})
def mon_outil(param):
    return "résultat que Jarvis lira"
```

Il est chargé au prochain démarrage.

## Réglages avancés (fichier `.env` dans le dossier de Jarvis)

- `JARVIS_MODEL` : `claude-sonnet-5-5` (rapide, conseillé pour la voix) ou `claude-opus-5-5` (plus malin, plus lent et plus cher).
- `JARVIS_WHISPER_MODEL` : `small` par défaut ; `medium` ou `large-v3` si tu as une carte graphique NVIDIA (meilleure compréhension) ; `base` si le PC est lent.
- `JARVIS_VOICE` : `fr-FR-RemyMultilingualNeural` par défaut ; toute voix Edge (`fr-FR-VivienneMultilingualNeural`, `fr-CA-ThierryNeural`...) ou `elevenlabs:<identifiant>` avec `ELEVENLABS_API_KEY` (compte gratuit sur elevenlabs.io, environ 10 minutes de voix par mois).
- `JARVIS_WAKE_BY_NAME` / `JARVIS_WAKE_WHISPER_MODEL` : réveil par le nom (`1`, modèle `base`). Le modèle « Hey Jarvis » d'openWakeWord ne reconnaît que la prononciation anglaise ; `JARVIS_WAKEWORD_THRESHOLD` règle sa sensibilité.
- `JARVIS_CLAP` / `JARVIS_CLAP_MIN_PEAK` : double clap (`0` pour le couper) ; monte `JARVIS_CLAP_MIN_PEAK` (4000) s'il se déclenche tout seul, baisse-le (1500) s'il n'entend pas tes claquements.
- `JARVIS_FOLLOWUP_SECONDS` : durée d'écoute après chaque réponse.

## Coût

Par défaut, Jarvis réfléchit avec **ton abonnement Claude (Pro ou Max)** grâce à Claude Code, installé avec lui : aucun frais en plus, ses demandes comptent simplement dans les limites de ton abonnement. Whisper, le réveil et la voix Edge sont gratuits ; une voix ElevenLabs est gratuite jusqu'à environ 10 minutes par mois.

Dans les Réglages, tu peux passer en mode **clé API** (plus rapide de 2 à 3 secondes, mais facturé à l'usage en plus de l'abonnement : quelques centimes par demande).

## Dépannage

- **Il ne m'entend pas** : vérifie le micro par défaut dans Windows (Paramètres > Son) et commence ta phrase par « Jarvis ». Au premier lancement, le réveil par le nom attend la fin du téléchargement de son modèle (150 Mo).
- **Il s'entend lui-même parler** : utilise un casque.
- **Pas de voix** : Edge TTS a besoin d'Internet ; sinon Jarvis bascule sur la voix Windows.
- **Erreur pip sur une bibliothèque** : utilise Python 3.11 ou 3.12 (3.13 n'a pas encore toutes les dépendances).
- **OBS ne répond pas** : OBS doit être ouvert, WebSocket activé, mot de passe correct.

## Structure

```
jarvis/
  gui.py        la fenêtre (orbe animée, conversation, réglages)
  engine.py     moteur : écoute, cerveau et voix en parallèle
  __main__.py   mode console
  ears.py       micro, mot d'éveil, détection de parole, Whisper
  voice.py      synthèse vocale interruptible
  claude_brain.py  cerveau « abonnement » : Claude Code + pont vers les outils
  mcp_bridge.py serveur MCP qui relaie les outils de Jarvis à Claude Code
  brain.py      cerveau « clé API » : Claude + boucle d'outils en streaming
  tools/        système, fichiers, médias, OBS, vidéo, jeux, mémoire, méta
plugins/        tes outils (et ceux que Jarvis crée)
installeur/     script NSIS de l'installeur Windows
data/           mémoire à long terme (memoire.json)
```
