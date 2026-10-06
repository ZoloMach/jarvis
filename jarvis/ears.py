"""Écoute : micro en continu, réveil (nom, « Hey Jarvis », double clap), détection de parole (VAD) et transcription.

Le modèle « hey_jarvis » d'openWakeWord n'a appris que la prononciation anglaise : prononcé à la française, il ne
réagit presque pas. Jarvis repère donc aussi son nom avec Whisper : au début de chaque phrase entendue pendant la
veille, il transcrit les deux premières secondes avec un petit modèle rapide et se réveille s'il y entend son nom.
"""
import collections
import difflib
import queue
import re
import threading
import time
import unicodedata

import numpy as np
import sounddevice as sd

from . import config

SR = 16000
FRAME = 1280  # 80 ms, taille attendue par openWakeWord
VAD_FRAME = 320  # 20 ms pour webrtcvad
NAME_CHECK_SECONDS = 2.0  # durée du début de phrase où l'on cherche le nom
PRE_FRAMES = 5  # ~400 ms gardées avant le début de la parole


def _norm(word):
    word = unicodedata.normalize("NFKD", word.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", word)


def _close(word, target):
    """Le mot transcrit ressemble-t-il au nom ? (« Jarvi », « Charvis », « Djarvis »... mais pas « avis »)"""
    if word == target:
        return True
    if len(word) < 4 or difflib.SequenceMatcher(None, word, target).ratio() < 0.75:
        return False
    same_start = word[0] == target[0] or (target == "jarvis" and word[0] in "cdgz")
    return same_start


def _find_name(text, name=None):
    """Position de la fin du nom dans `text` (None s'il n'y est pas). Gère « J'arvis » coupé en deux mots."""
    target = _norm(name or config.NAME)
    if not target:
        return None
    tokens = [(_norm(m.group()), m.end()) for m in re.finditer(r"[^\W\d_]+", text)]
    for i, (word, end) in enumerate(tokens):
        if _close(word, target):
            return end
        if len(word) <= 2 and i + 1 < len(tokens) and _close(word + tokens[i + 1][0], target):
            return tokens[i + 1][1]
    return None


def has_name(text, name=None):
    """Vrai si `text` contient le nom de l'assistant, même un peu mal transcrit."""
    return _find_name(text, name) is not None


def after_name(text, name=None):
    """Ce qui suit le nom dans la phrase (« Hey Jarvis, ouvre Discord » -> « ouvre Discord »)."""
    end = _find_name(text, name)
    return (text[end:] if end is not None else text).strip(" ,.!?;:")


class ClapDetector:
    """Repère deux claquements de mains rapprochés : deux bruits très brefs et forts à moins d'une seconde d'écart.

    Un claquement monte d'un coup et retombe en moins de 200 ms, alors que la voix ou la musique restent fortes
    plus longtemps : ce qui dure est ignoré. Un claquement est aussi riche en aigus, contrairement aux voyelles.
    Les petits bruits secs (touches du clavier, objet posé) sont suivis : un claquement doit nettement les dépasser,
    et les deux claquements doivent être entourés de calme. Trois claquements ou plus (applaudissements) ne
    déclenchent rien.
    """

    SUB = 160  # analyse par tranches de 10 ms
    DECAY = 0.2  # un bruit sec doit être retombé en moins de 200 ms
    GAP = (0.12, 0.9)  # écart entre les deux claquements (secondes)
    QUIET_BEFORE = 0.6  # aucun bruit sec juste avant le premier claquement...
    QUIET_AFTER = 0.45  # ... ni juste après le second

    def __init__(self, min_peak=2500, ratio=6.0):
        self.min_peak = min_peak  # pic minimal d'un claquement (échelle int16, 32767 = maximum)
        self.ratio = ratio  # combien de fois plus fort que le bruit de fond
        self.reset()

    def reset(self):
        self.t = 0.0
        self.floor = 200.0
        self.prev = 200.0
        self.pending = None  # bruit sec en cours de vérification : [début, énergie max, pic max]
        self.last_noise = -10.0  # instant du dernier bruit sec qui n'était pas un claquement
        self.recent = collections.deque(maxlen=40)  # (instant, énergie) des derniers bruits secs
        self.claps = []
        self.armed = None
        self.strength = 0.0

    def feed(self, frame):
        """Analyse 80 ms de son ; renvoie True quand un double clap vient d'être entendu."""
        x = frame.astype(np.float32)
        hit = False
        for i in range(0, len(x), self.SUB):
            sub = x[i : i + self.SUB]
            rms = float(np.sqrt(np.mean(sub**2))) + 1.0
            peak = float(np.max(np.abs(sub)))
            # Part d'aigus : ~1,4 pour un bruit blanc ou un claquement, bien moins pour une voyelle.
            bright = float(np.sqrt(np.mean(np.diff(sub) ** 2))) / rms
            self.t += len(sub) / SR
            hit = self._step(rms, peak, bright) or hit
        return hit

    def _step(self, rms, peak, bright=1.0):
        if self.pending:
            p = self.pending
            p[1], p[2] = max(p[1], rms), max(p[2], peak)
            if rms < p[1] * 0.25 and self.t - p[0] >= 0.02:  # vite retombé : bruit sec
                self.pending = None
                self._transient(*p)
            elif self.t - p[0] > self.DECAY:  # dure trop : voix, musique, porte...
                self.pending = None
                self._cancel()
        elif peak >= self.min_peak / 3 and rms >= 3 * self.floor and rms >= 3 * self.prev and bright >= 0.6:
            self.pending = [self.t, rms, peak]
        else:
            # Bruit de fond : descend vite, remonte lentement (un bruit soudain ne le fausse pas).
            k = 0.1 if rms < self.floor else 0.002
            self.floor = max(30.0, self.floor + k * (rms - self.floor))
        self.prev = rms
        if self.armed is not None and self.t - self.armed >= self.QUIET_AFTER:
            self.armed = None
            self.claps.clear()
            return True
        return False

    def _cancel(self):
        self.claps.clear()
        self.armed = None

    def _transient(self, start, level, peak):
        others = [lv for t, lv in self.recent if start - t <= 10]
        self.recent.append((start, level))
        loud = peak >= self.min_peak and level >= self.ratio * self.floor
        # Pendant qu'on tape au clavier, chaque touche fait un bruit sec : un claquement doit nettement les dépasser.
        if loud and len(others) >= 3:
            loud = level >= 2.5 * float(np.median(others))
        if not loud or self.armed is not None:  # autre bruit, ou troisième claquement (applaudissements)
            self.last_noise = start
            self._cancel()
            return
        self.claps = [t for t in self.claps if start - t <= self.GAP[1]] + [start]
        self.strength = level / max(self.floor, 1.0)
        if len(self.claps) >= 2:
            first, second = self.claps[-2], self.claps[-1]
            calm_before = first - self.last_noise >= self.QUIET_BEFORE and (
                len(self.claps) < 3 or first - self.claps[-3] >= self.QUIET_BEFORE
            )
            if self.GAP[0] <= second - first <= self.GAP[1] and calm_before:
                self.armed = start


class NameSpotter:
    """Petit Whisper rapide (« base ») qui dit si le nom de l'assistant est prononcé au début d'une phrase."""

    def __init__(self, shared=None):
        self.model = shared  # même modèle que la transcription s'il est déjà de cette taille
        if shared is None:
            threading.Thread(target=self._load, daemon=True, name="jarvis-nom").start()

    def _load(self):
        try:
            from faster_whisper import WhisperModel

            self.model = WhisperModel(config.WAKE_WHISPER_MODEL, device="cpu", compute_type="int8")
            print(f"[réveil] Réveil par le nom prêt (Whisper « {config.WAKE_WHISPER_MODEL} »).", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[réveil] Réveil par le nom indisponible : {e}", flush=True)

    @property
    def ready(self):
        return self.model is not None

    def heard_name(self, audio):
        t0 = time.time()
        segments, _ = self.model.transcribe(audio, language=config.LANGUAGE, beam_size=1, vad_filter=False,
                                            condition_on_previous_text=False, without_timestamps=True,
                                            initial_prompt=f"{config.NAME} !")  # fmt: skip
        text = " ".join(s.text.strip() for s in segments).strip()
        found = has_name(text)
        if found:  # on ne note pas le reste : ce que l'utilisateur dit à d'autres ne regarde pas le journal
            print(f"[réveil] nom entendu dans {text!r} ({time.time() - t0:.2f} s).", flush=True)
        return found


class Ears:
    def __init__(self, use_wakeword=True):
        import webrtcvad

        self.vad = webrtcvad.Vad(2)
        self.q: queue.Queue = queue.Queue()
        self.use_wakeword = use_wakeword
        self.oww = None
        self.spotter = None
        self.claps = ClapDetector(min_peak=config.CLAP_MIN_PEAK)
        self.level = 0.0
        if use_wakeword:
            self._init_wakeword()
        print("[écoute] Chargement de Whisper...")
        from faster_whisper import WhisperModel

        # Sur processeur, int8 est rapide et léger ; « auto » tente la carte graphique NVIDIA si CUDA est installé.
        device = config.WHISPER_DEVICE
        compute = "int8" if device == "cpu" else "default"
        try:
            self.whisper = WhisperModel(config.WHISPER_MODEL, device=device, compute_type=compute)
        except Exception as e:  # noqa: BLE001 - carte graphique mal configurée : on se rabat sur le processeur
            print(f"[écoute] Whisper sur {device} impossible ({e}), passage sur le processeur.")
            self.whisper = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
        print(f"[écoute] Whisper « {config.WHISPER_MODEL} » prêt.", flush=True)
        if use_wakeword and config.WAKE_BY_NAME:
            same = config.WAKE_WHISPER_MODEL == config.WHISPER_MODEL
            self.spotter = NameSpotter(shared=self.whisper if same else None)
        self.stream = sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=FRAME, callback=self._cb)
        self.stream.start()

    def _init_wakeword(self):
        try:
            import openwakeword
            from openwakeword.model import Model

            try:
                openwakeword.utils.download_models([config.WAKEWORD_MODEL])
            except Exception as e:  # noqa: BLE001
                print(f"[écoute] Téléchargement du modèle de mot d'éveil : {e}")
            self.oww = Model(wakeword_models=[config.WAKEWORD_MODEL], inference_framework="onnx")
        except Exception as e:  # noqa: BLE001 - le réveil par le nom et le double clap suffisent
            print(f"[écoute] « Hey {config.NAME} » à l'anglaise indisponible : {e}")

    def _cb(self, indata, frames, t, status):
        frame = indata[:, 0].copy()
        # Niveau du micro entre 0 et 1, pour l'animation de la fenêtre.
        self.level = min(1.0, float(np.sqrt(np.mean(frame.astype(np.float32) ** 2))) / 6000)
        self.q.put(frame)

    def clear(self):
        while not self.q.empty():
            try:
                self.q.get_nowait()
            except queue.Empty:
                break

    def _frame(self, timeout=None):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return None

    # --- Réveil ---
    def heard_wakeword(self, frame):
        if not self.oww:
            return False
        scores = self.oww.predict(frame)
        if max(scores.values()) >= config.WAKEWORD_THRESHOLD:
            self.oww.reset()
            return True
        return False

    def wait_wake(self, interrupt=None):
        """Veille jusqu'à un réveil, ou jusqu'à ce que `interrupt()` soit vrai (renvoie alors None).

        Renvoie ("mot", None) pour « Hey Jarvis » à l'anglaise, ("nom", audio) quand le nom est dit en début de
        phrase (audio = la phrase entière, qui peut déjà contenir la demande) ou ("clap", None) pour un double clap.
        """
        self.clear()
        if self.oww:
            self.oww.reset()
        self.claps.reset()
        pre = collections.deque(maxlen=PRE_FRAMES)
        seg, streak, silent, checked = [], 0, 0.0, False
        while True:
            if interrupt and interrupt():
                return None
            f = self._frame(timeout=0.1)
            if f is None:
                continue
            if self.heard_wakeword(f):
                print(f"[réveil] « Hey {config.NAME} » entendu.", flush=True)
                return ("mot", None)
            if config.CLAP_WAKE and self.claps.feed(f):
                print(f"[réveil] double clap (force {self.claps.strength:.0f} fois le bruit de fond).", flush=True)
                return ("clap", None)
            if not (config.WAKE_BY_NAME and self.spotter and self.spotter.ready):
                continue
            speech = self._is_speech(f)
            if not seg:
                pre.append(f)
                streak = streak + 1 if speech else 0
                if streak >= 2:
                    seg, silent, checked = list(pre), 0.0, False
                continue
            seg.append(f)
            silent = 0.0 if speech else silent + FRAME / SR
            ended = silent >= 0.5
            if not checked and (len(seg) * FRAME / SR >= NAME_CHECK_SECONDS or ended):
                checked = True
                head = np.concatenate(seg[: int(NAME_CHECK_SECONDS * SR / FRAME)]).astype(np.float32) / 32768.0
                if self.spotter.heard_name(head):
                    return ("nom", self._finish_phrase(seg, silent))
            if ended or len(seg) * FRAME / SR > 30:
                seg, streak = [], 0
                pre.clear()

    def wait_wakeword(self, interrupt=None):
        """Compatibilité : True dès un réveil, quel qu'il soit."""
        return self.wait_wake(interrupt) is not None

    def _finish_phrase(self, seg, silent, end_silence=0.9, max_len=30.0):
        """Continue d'enregistrer la phrase commencée jusqu'au silence ; renvoie toute la phrase."""
        speech = list(seg)
        while silent < end_silence and len(speech) * FRAME / SR < max_len:
            f = self._frame(timeout=0.5)
            if f is None:
                break
            speech.append(f)
            silent = 0.0 if self._is_speech(f) else silent + FRAME / SR
        return np.concatenate(speech).astype(np.float32) / 32768.0

    def poll_wakeword(self):
        """Non bloquant : traite les trames en attente, True si le mot d'éveil a été entendu (pour interrompre Jarvis)."""
        if not self.oww:
            return False
        hit = False
        while not self.q.empty():
            f = self._frame(0)
            if f is not None and self.heard_wakeword(f):
                hit = True
        return hit

    # --- Enregistrement d'une phrase ---
    def _is_speech(self, frame):
        voiced = sum(self.vad.is_speech(frame[i : i + VAD_FRAME].tobytes(), SR) for i in range(0, FRAME, VAD_FRAME))
        return voiced >= 2

    def record(self, start_timeout=6.0, end_silence=0.9, max_len=30.0):
        """Attend que l'utilisateur parle (au plus `start_timeout` s), puis enregistre jusqu'à un silence.

        Renvoie un tableau float32 ou None si personne n'a parlé.
        """
        self.clear()
        pre = collections.deque(maxlen=4)  # garde ~300 ms avant le début de la parole
        t0 = time.time()
        speech, started, silent, streak = [], False, 0.0, 0
        while True:
            f = self._frame(timeout=0.5)
            if f is None:
                if not started and start_timeout is not None and time.time() - t0 > start_timeout:
                    return None
                continue
            if not started:
                pre.append(f)
                streak = streak + 1 if self._is_speech(f) else 0
                if streak >= 2:
                    started = True
                    speech.extend(pre)
                elif start_timeout is not None and time.time() - t0 > start_timeout:
                    return None
                continue
            speech.append(f)
            silent = 0.0 if self._is_speech(f) else silent + FRAME / SR
            if silent >= end_silence or len(speech) * FRAME / SR > max_len:
                break
        return np.concatenate(speech).astype(np.float32) / 32768.0

    def transcribe(self, audio):
        segments, _ = self.whisper.transcribe(
            audio, language=config.LANGUAGE, beam_size=1, vad_filter=True, initial_prompt=f"{config.NAME}, "
        )
        return " ".join(s.text.strip() for s in segments).strip()
