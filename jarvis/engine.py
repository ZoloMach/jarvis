"""Moteur de Jarvis indépendant de l'affichage : écoute, cerveau et voix dans des fils séparés.

L'interface reçoit les événements par `post(type, données)` :
  state   -> "chargement" | "veille" | "ecoute" | "reflexion" | "pause" | "texte"
  user    -> phrase de l'utilisateur
  jarvis  -> phrase de Jarvis
  tool    -> nom de l'outil utilisé
  info / error -> message à afficher
  confirm -> (action, détails, holder) : demande de confirmation ; l'interface remplit holder["ok"] puis holder["event"].set()
"""
import queue
import threading
import time
import traceback
import unicodedata

from . import config, tools
from .brain import Brain
from .voice import BEEP_SLEEP, BEEP_WAKE, Speaker

STOP_WORDS = ("merci jarvis", "c'est tout", "ce sera tout", "au revoir", "bonne nuit", "laisse tomber", "stop jarvis")
YES = ("oui", "ouais", "vas-y", "vas y", "confirme", "d'accord", "ok", "go", "fais-le", "fais le", "absolument", "yes")
NO = ("non", "annule", "surtout pas", "stop", "arrete")
# Envoyé au cerveau quand on tape deux fois dans ses mains (compétence « routine-demarrage » du dossier de travail).
ROUTINE_REQUEST = "Double clap : lance ma routine de démarrage."


def norm(s):
    s = s.replace("’", "'")
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return s.strip(" .!?,")


def is_stop(text):
    t = norm(text)
    return any(t.startswith(norm(w)) for w in STOP_WORDS)


def is_yes(text):
    words = norm(text).replace(",", " ").split()
    t = " ".join(words)
    if any(w in words for w in NO):
        return False
    return any(y in words or (" " in y and y in t) for y in YES)


def is_no(text):
    words = norm(text).replace(",", " ").split()
    return any(w in words for w in NO)


class Engine:
    def __init__(self, post):
        self.post = post
        self.inputs: queue.Queue = queue.Queue()
        self.mic_enabled = True
        self.ptt = threading.Event()
        self.busy = threading.Event()
        self.ears = None
        self.speaker = None
        self.brain = None

    # --- API pour l'interface ---
    def start(self):
        threading.Thread(target=self._boot, daemon=True, name="jarvis-boot").start()

    def send_text(self, text):
        """Message tapé au clavier."""
        if self.speaker:
            self.speaker.stop()
        self.busy.set()
        self.inputs.put(text)

    def push_to_talk(self):
        """Écoute tout de suite, sans attendre « Hey Jarvis »."""
        if self.speaker:
            self.speaker.stop()
        self.ptt.set()

    def cancel(self):
        """Bouton « Arrêter » : coupe la parole et abandonne la demande en cours."""
        if self.speaker:
            self.speaker.stop()
        if self.busy.is_set() and hasattr(self.brain, "cancel"):
            self.brain.cancel()
            self.post("info", "Demande arrêtée.")

    def set_mic(self, enabled):
        self.mic_enabled = enabled

    @property
    def speaking(self):
        return bool(self.speaker and self.speaker.speaking)

    @property
    def mic_level(self):
        return self.ears.level if self.ears else 0.0

    def say(self, text):
        text = text.strip()
        if text:
            self.post("jarvis", text)
            self.speaker.say(text)

    def load_brain(self):
        """(Re)crée le cerveau selon le réglage : abonnement Claude (Claude Code) ou clé API."""
        if config.BRAIN == "api":
            self.brain = Brain()
        else:
            from .claude_brain import ClaudeCodeBrain

            self.brain = ClaudeCodeBrain()

    # --- Démarrage ---
    def _boot(self):
        self.post("state", "chargement")
        tools.load_all()
        self.speaker = Speaker()
        tools.meta.notify = self.say  # les rappels sont annoncés à voix haute
        try:
            self.load_brain()
        except Exception as e:  # noqa: BLE001
            self.post("error", str(e))
        threading.Thread(target=self._process_loop, daemon=True, name="jarvis-brain").start()
        try:
            self.post("info", "Préparation de la reconnaissance vocale. Au tout premier lancement, "
                      "Jarvis télécharge ses modèles (quelques minutes).")  # fmt: skip
            from .ears import Ears

            self.ears = Ears(use_wakeword=True)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.post("error", f"Micro indisponible ({e}). Tu peux quand même m'écrire en bas de la fenêtre.")
        self.say(f"{config.NAME} en ligne. À votre service, {config.USER_NAME}.")
        if self.ears:
            clap = " Tape deux fois dans tes mains pour ta routine de démarrage." if config.CLAP_WAKE else ""
            self.post("info", f"Dis « {config.NAME} » en début de phrase (« {config.NAME}, ouvre Discord ») "
                      f"ou clique sur Parler.{clap}")  # fmt: skip
            self._voice_loop()
        else:
            self.post("state", "texte")

    # --- Écoute ---
    def _listen(self, timeout):
        audio = self.ears.record(start_timeout=timeout)
        if audio is None:
            return None
        self.post("state", "reflexion")
        t0 = time.time()
        text = self.ears.transcribe(audio)
        print(f"[écoute] {len(audio) / 16000:.1f} s d'audio transcrites en {time.time() - t0:.1f} s : {text!r}", flush=True)
        return text

    def _voice_loop(self):
        in_conversation = False
        while True:
            try:
                if not self.mic_enabled:
                    self.post("state", "pause")
                    in_conversation = False
                    while not self.mic_enabled:
                        time.sleep(0.1)
                    continue
                if self.busy.is_set():  # une demande tapée au clavier est en cours
                    time.sleep(0.05)
                    continue

                text = None
                if not in_conversation:
                    self.post("state", "veille")
                    woke = self.ears.wait_wake(
                        interrupt=lambda: self.ptt.is_set() or not self.mic_enabled or self.busy.is_set()
                    )
                    if woke is None and not self.ptt.is_set():
                        continue
                    self.ptt.clear()
                    self.speaker.stop()
                    if woke and woke[0] == "nom":
                        from .ears import after_name

                        # « Jarvis, ouvre Discord » : la demande est déjà dans la phrase qui l'a réveillé.
                        self.post("state", "reflexion")
                        heard = self.ears.transcribe(woke[1])
                        print(f"[écoute] {len(woke[1]) / 16000:.1f} s d'audio au réveil : {heard!r}", flush=True)
                        if is_stop(heard):  # « Merci Jarvis » dit après coup : rien à faire
                            continue
                        if len(after_name(heard)) >= 4:
                            text = heard
                    elif woke and woke[0] == "clap":
                        text = ROUTINE_REQUEST
                    self.speaker.beep(BEEP_WAKE)
                    self.speaker.wait()
                    timeout = 6
                else:
                    timeout = config.FOLLOWUP_SECONDS

                if text is None:
                    self.post("state", "ecoute")
                    text = self._listen(timeout)
                if text is None:
                    if in_conversation:
                        self.speaker.beep(BEEP_SLEEP)
                    in_conversation = False
                    continue
                if not text:
                    continue
                if is_stop(text):
                    self.post("user", text)
                    self.say("À votre service.")
                    self.speaker.wait()
                    in_conversation = False
                    continue

                self.busy.set()
                self.inputs.put(text)
                while self.busy.is_set():
                    time.sleep(0.05)
                # Pendant qu'il parle, dire « Hey Jarvis » le coupe.
                self.ears.clear()
                self.speaker.wait(poll=self.ears.poll_wakeword)
                in_conversation = True
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self.post("error", f"Problème d'écoute : {e}")
                time.sleep(1)

    # --- Cerveau ---
    def _process_loop(self):
        import anthropic

        from .claude_brain import ClaudeCodeError, explain_error

        while True:
            text = self.inputs.get()
            self.busy.set()
            self.post("user", text)
            self.post("state", "reflexion")
            try:
                if self.brain is None:
                    self.load_brain()
                self.brain.ask(text, self.say, self._confirm, on_tool=lambda name, args: self.post("tool", name))
            except ClaudeCodeError as e:
                self.post("error", explain_error(str(e)))
                self.speaker.say("Je n'arrive pas à réfléchir pour le moment, regarde le message dans la fenêtre.")
            except anthropic.AuthenticationError:
                self._repair_history()
                self.post("error", "Ta clé API Claude est refusée. Ouvre les Réglages pour la corriger.")
                self.speaker.say("Ma clé d'accès est refusée. Vérifie-la dans les réglages.")
            except anthropic.APIConnectionError:
                self._repair_history()
                self.post("error", "Pas de connexion à Internet, ou Claude est injoignable.")
                self.speaker.say("Je n'arrive pas à me connecter.")
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                self._repair_history()
                msg = str(e)
                if "credit" in msg.lower():
                    self.post("error", "Ton compte Claude n'a plus de crédit : recharge-le sur console.anthropic.com.")
                else:
                    self.post("error", f"Erreur : {msg[:300]}")
                self.speaker.say("Désolé, j'ai rencontré un problème.")
            finally:
                self.busy.clear()

    def _repair_history(self):
        """Après une erreur, retire la fin de conversation incomplète pour pouvoir continuer."""
        h = getattr(self.brain, "history", None)
        while h and not (
            h[-1]["role"] == "assistant" and not any(b.get("type") == "tool_use" for b in h[-1]["content"])
        ):
            h.pop()

    def _confirm(self, action, details=""):
        self.say(f"Je dois confirmer avant de {action}. Je le fais ?")
        holder = {"event": threading.Event(), "ok": None}
        self.post("confirm", (action, details, holder))
        if self.ears and self.mic_enabled:
            self.speaker.wait()
            deadline = time.time() + 60
            while not holder["event"].is_set() and time.time() < deadline:
                answer = self._listen(3)
                if answer:
                    self.post("user", answer)
                    if is_yes(answer) or is_no(answer):
                        holder["ok"] = is_yes(answer)
                        holder["event"].set()
            self.post("state", "reflexion")
        holder["event"].wait(timeout=120)
        holder["event"].set()  # ferme la fenêtre de confirmation si elle est encore ouverte
        if not holder["ok"]:
            self.say("Très bien, j'annule.")
        return bool(holder["ok"])
