"""Lanceur de la fenêtre Jarvis (double-clic, sans console)."""
import datetime
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
(ROOT / "data").mkdir(exist_ok=True)
LOG = ROOT / "data" / "jarvis.log"
# Le journal repart de zéro quand il dépasse 2 Mo (l'ancien est gardé en jarvis.old.log).
if LOG.exists() and LOG.stat().st_size > 2_000_000:
    LOG.replace(LOG.with_name("jarvis.old.log"))


class TimestampedLog:
    """Sans console, les messages vont dans data/jarvis.log, chaque ligne précédée de l'heure."""

    def __init__(self, path):
        self.f = open(path, "a", encoding="utf-8", buffering=1)
        self.start = True

    def write(self, text):
        for part in text.splitlines(keepends=True):
            if self.start:
                self.f.write(datetime.datetime.now().strftime("%H:%M:%S "))
            self.f.write(part)
            self.start = part.endswith("\n")
        return len(text)

    def flush(self):
        self.f.flush()


sys.stdout = sys.stderr = TimestampedLog(LOG)
print(f"===== Démarrage de Jarvis, {datetime.datetime.now():%d/%m/%Y %H:%M} =====")

from jarvis import updater  # noqa: E402

# Jarvis vérifie s'il existe une nouvelle version ; s'il vient d'en installer une, il redémarre dessus.
AFTER_UPDATE = "--apres-maj" in sys.argv
if not AFTER_UPDATE and updater.at_startup(force="--maj" in sys.argv):
    updater.restart("--apres-maj")
    sys.exit(0)

try:
    from jarvis.gui import main

    main(updater.news())
except Exception:
    traceback.print_exc()
    # Une mise à jour qui empêche Jarvis de démarrer est annulée : retour à la version précédente.
    if AFTER_UPDATE and updater.rollback():
        updater.restart()
    sys.exit(1)
