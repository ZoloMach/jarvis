"""Dossier de travail de Jarvis : sa fiche d'identité, sa mémoire, ses compétences et ses projets.

En mode abonnement, Claude Code travaille dans ce dossier : il relit CLAUDE.md à chaque demande, crée les
applications et documents demandés dans projets/ et utilise les compétences rangées dans .claude/skills/.
Le dossier est dans les Documents de l'utilisateur pour qu'il puisse le voir et le modifier ; les fichiers
de départ ne sont créés que s'ils n'existent pas, jamais remplacés.
"""
import platform
from pathlib import Path

from . import config

CLAUDE_MD = """# Fiche de {name}

Ce dossier est l'espace de travail de {name}, l'assistant vocal de {user}. {user} peut modifier ce fichier :
{name} le relit à chaque demande.

## Qui est {user}
- (Complète cette partie quand tu apprends des choses importantes sur {user} : métier, projets, chaîne,
  jeux préférés, ville pour la météo, habitudes.)

## Comment {name} travaille
- Tout ce que tu crées (applications, documents, scripts, posts) va dans projets/, un sous-dossier par projet.
  Ouvre ensuite le résultat pour {user} avec l'outil mcp__jarvis__ouvrir.
- Les notes longues utiles pour plus tard (suivi de projets, idées, listes) vont dans memoire/.
- Tes compétences sont dans .claude/skills/ : sers-t'en dès qu'une demande y correspond. Quand {user} te demande
  d'apprendre à faire quelque chose, crée une nouvelle compétence (compétence « nouvelle-competence »).
- En dehors de ce dossier, passe par tes outils Jarvis : ils demandent confirmation pour les actions sensibles.
"""

SKILLS = {
    "petite-application": """---
name: petite-application
description: Créer une petite application, un jeu ou un outil qui s'ouvre dans le navigateur (morpion, quiz, calculatrice, minuteur, page de présentation...). À utiliser quand {user} demande de coder, développer ou créer une appli, un jeu, une page ou un site.
---

1. Crée le dossier projets/<nom-court>/ et écris-y index.html : une page autonome (HTML, CSS et JavaScript dans
   le même fichier, rien à installer), soignée, en français, utilisable à la souris.
2. Ouvre-la avec mcp__jarvis__ouvrir (chemin complet du fichier) ; si {user} a précisé un écran, passe-le dans
   le paramètre ecran.
3. Dis en une phrase que c'est prêt et comment s'en servir.

Pour une modification, édite le fichier existant puis rouvre-le.
""",
    "post-linkedin": """---
name: post-linkedin
description: Rédiger un post LinkedIn (ou pour un autre réseau social) à partir d'un sujet, d'une actualité ou d'une idée de {user}.
---

1. Si le sujet est une actualité, vérifie les faits avec WebSearch.
2. Écris le post : une accroche forte en première ligne, trois à cinq paragraphes courts, une question ou un
   appel à l'action à la fin, trois hashtags au plus. Ton direct et personnel, à la première personne, comme
   {user} l'écrirait. Si memoire/style-posts.md existe, respecte-le.
3. Enregistre-le dans projets/posts/<date>-<sujet>.md, copie-le dans le presse-papiers avec
   mcp__jarvis__copier_presse_papiers, puis ouvre le fichier.
4. À voix haute, résume l'angle choisi en une phrase et dis que le texte est copié, prêt à coller.

Quand {user} corrige un post, note ses préférences dans memoire/style-posts.md.
""",
    "briefing": """---
name: briefing
description: Faire le point du jour quand {user} dit bonjour, demande un briefing, « quoi de neuf aujourd'hui » ou « fais-moi le point ».
---

En quatre phrases au plus, à voix haute :
1. Le jour et l'heure.
2. La météo du jour là où vit {user} (sa ville est dans CLAUDE.md ; sinon demande-la une fois et note-la dans
   CLAUDE.md), avec WebSearch.
3. Les minuteurs en cours (mcp__jarvis__minuteurs) et ce qui est noté dans memoire/a-faire.md s'il existe.
4. Une actualité qui peut l'intéresser d'après ses centres d'intérêt (CLAUDE.md).
""",
    "nouvelle-competence": """---
name: nouvelle-competence
description: Apprendre une nouvelle façon de faire quand {user} dit « apprends à... », « crée-toi une compétence pour... », ou quand il répète souvent la même demande en plusieurs étapes.
---

1. Choisis un nom court en minuscules avec des tirets (exemple : resume-video).
2. Écris .claude/skills/<nom>/SKILL.md qui commence par ces lignes :
       ---
       name: <nom>
       description: <quand l'utiliser, avec les mots que {user} emploierait>
       ---
   puis les étapes précises, les outils à utiliser et la forme de la réponse.
3. Si la compétence doit faire tourner du code sur le PC (pas seulement écrire ou chercher), crée plutôt un
   outil avec mcp__jarvis__creer_outil.
4. Confirme en une phrase ce que tu sais faire désormais et la phrase qui le déclenche. La compétence sera
   disponible dès la prochaine conversation.
""",
}


def documents_dir():
    """Dossier « Documents » de l'utilisateur (sous Windows, il peut être déplacé, par exemple dans OneDrive)."""
    if platform.system() == "Windows":
        import ctypes

        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:  # 5 = Mes documents
            return Path(buf.value)
    return Path.home() / "Documents"


def path():
    return Path(config.WORKSPACE).expanduser() if config.WORKSPACE else documents_dir() / config.NAME


def ensure():
    """Crée le dossier de travail et ses fichiers de départ s'ils manquent. Renvoie son chemin."""
    root = path()
    values = {"name": config.NAME, "user": config.USER_NAME}
    files = {"CLAUDE.md": CLAUDE_MD}
    files |= {f".claude/skills/{name}/SKILL.md": text for name, text in SKILLS.items()}
    for sub in ("projets", "memoire"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        target = root / rel
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text.format(**values), encoding="utf-8")
    return root
