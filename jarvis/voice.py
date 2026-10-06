"""Synthèse vocale : Edge TTS (voix neuronales gratuites, nécessite Internet) ou ElevenLabs (voix plus humaines,
avec une clé), repli sur pyttsx3 hors ligne."""
import asyncio
import json
import queue
import ssl
import threading
import time
import urllib.request

import numpy as np
import sounddevice as sd

from . import config

SR = 24000
# Voix Edge proposées dans les réglages. Les « Multilingual » sont les plus récentes et les plus naturelles.
EDGE_VOICES = {
    "Rémy (France, la plus naturelle)": "fr-FR-RemyMultilingualNeural",
    "Vivienne (France, la plus naturelle)": "fr-FR-VivienneMultilingualNeural",
    "Henri (France)": "fr-FR-HenriNeural",
    "Denise (France)": "fr-FR-DeniseNeural",
    "Éloïse (France)": "fr-FR-EloiseNeural",
    "Antoine (Québec)": "fr-CA-AntoineNeural",
    "Thierry (Québec)": "fr-CA-ThierryNeural",
    "Gérard (Belgique)": "fr-BE-GerardNeural",
    "Fabrice (Suisse)": "fr-CH-FabriceNeural",
    "Andrew (léger accent américain)": "en-US-AndrewMultilingualNeural",
    "Brian (léger accent américain)": "en-US-BrianMultilingualNeural",
    "William (léger accent australien)": "en-AU-WilliamMultilingualNeural",
}
# Ton de la voix (débit, hauteur), au choix dans les réglages.
TONES = {
    "Posé et grave, façon JARVIS": ("-8%", "-6Hz"),
    "Naturel": ("+0%", "+0Hz"),
    "Plus rapide": ("+10%", "+0Hz"),
}
DEFAULT_VOICE = "fr-FR-RemyMultilingualNeural"
FALLBACK_VOICE = "fr-FR-HenriNeural"  # la plus ancienne, toujours disponible
SAMPLE = "Bonjour {user}. Tous les systèmes sont opérationnels. Qu'est-ce que je lance pour vous ?"
ELEVEN_URL = "https://api.elevenlabs.io/v1"
ELEVEN_PREFIX = "elevenlabs:"


def _https(url, key, body=None, timeout=30):
    ctx = ssl.create_default_context()
    try:  # certificats de Windows + ceux de certifi
        import certifi

        ctx.load_verify_locations(certifi.where())
    except Exception:  # noqa: BLE001
        pass
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"xi-api-key": key, "Content-Type": "application/json",
                                                          "User-Agent": "Jarvis"})  # fmt: skip
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:  # noqa: S310 - adresse https fixe
        return r.read()


def elevenlabs_voices(key, timeout=10):
    """Voix du compte ElevenLabs, pour les réglages : {nom affiché: "elevenlabs:<identifiant>"}."""
    data = json.loads(_https(f"{ELEVEN_URL}/voices", key, timeout=timeout))
    voices = {}
    for v in data.get("voices", []):
        accent = (v.get("labels") or {}).get("accent")
        voices[f"ElevenLabs : {v['name']}" + (f" ({accent})" if accent else "")] = ELEVEN_PREFIX + v["voice_id"]
    return voices


def _tone(freqs, dur=0.09, vol=0.25):
    parts = []
    for f in freqs:
        t = np.linspace(0, dur, int(SR * dur), False)
        env = np.minimum(1, np.minimum(t, dur - t) * 40)
        parts.append(np.sin(2 * np.pi * f * t) * env * vol)
    return (np.concatenate(parts) * 32767).astype(np.int16)


BEEP_WAKE = _tone([880, 1320])
BEEP_SLEEP = _tone([1320, 660])


class Speaker:
    """File d'attente de phrases jouées dans l'ordre, interruptible à tout moment."""

    def __init__(self, enabled=True):
        self.enabled = enabled
        self._q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._busy = threading.Event()
        self._offline = None
        self._eleven_pause = 0.0  # après une erreur ElevenLabs (clé, quota), on repasse sur Edge un moment
        threading.Thread(target=self._worker, daemon=True).start()

    # --- API publique ---
    def say(self, text):
        text = text.strip()
        if text:
            print(f"🤖 {config.NAME} : {text}")
            if self.enabled:
                self._q.put(("text", text, (None, None)))

    def preview(self, voice, tone=None, text=None):
        """Fait entendre une voix et un ton (bouton « Écouter » des réglages) sans changer ceux de Jarvis."""
        self.stop()
        self._eleven_pause = 0.0
        self._q.put(("text", text or SAMPLE.format(user=config.USER_NAME), (voice, tone)))

    def beep(self, sound=BEEP_WAKE):
        if self.enabled:
            self._q.put(("pcm", sound, (None, None)))

    def stop(self):
        """Coupe la parole immédiatement et vide la file."""
        self._stop.set()
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    @property
    def speaking(self):
        return self._busy.is_set() or not self._q.empty()

    def wait(self, poll=None):
        """Attend la fin de la parole. `poll()` peut renvoyer True pour interrompre (barge-in)."""
        while self.speaking:
            if poll and poll():
                self.stop()
                return True
            time.sleep(0.02)
        return False

    # --- interne ---
    def _worker(self):
        while True:
            kind, payload, (voice, tone) = self._q.get()
            self._busy.set()
            self._stop.clear()
            try:
                pcm = payload if kind == "pcm" else self._synth(payload, voice, tone)
                if pcm is not None and not self._stop.is_set():
                    self._play(pcm)
            except Exception as e:  # noqa: BLE001
                print(f"[voix] {e}")
            finally:
                if self._q.empty():
                    self._busy.clear()

    def _play(self, pcm):
        sd.play(pcm, SR)
        time.sleep(0.05)
        while sd.get_stream().active:
            if self._stop.is_set():
                sd.stop()
                return
            time.sleep(0.02)

    def _synth(self, text, voice=None, tone=None):
        voice = voice or config.TTS_VOICE or DEFAULT_VOICE
        rate, pitch = tone or (config.TTS_RATE, config.TTS_PITCH)
        if voice.startswith(ELEVEN_PREFIX):
            if config.ELEVENLABS_API_KEY and time.time() >= self._eleven_pause:
                try:
                    return self._elevenlabs(text, voice[len(ELEVEN_PREFIX) :])
                except Exception as e:  # noqa: BLE001
                    print(f"[voix] ElevenLabs indisponible ({e}) : voix Edge pendant 10 minutes.")
                    self._eleven_pause = time.time() + 600
            voice = DEFAULT_VOICE
        for v in dict.fromkeys((voice, FALLBACK_VOICE)):
            try:
                return self._edge(text, v, rate, pitch)
            except Exception as e:  # noqa: BLE001
                print(f"[voix] Edge TTS indisponible avec {v} ({e}).")
        print("[voix] Passage sur la voix hors ligne.")
        self._say_offline(text)
        return None

    def _elevenlabs(self, text, voice_id):
        body = {"text": text, "model_id": config.ELEVENLABS_MODEL}
        if "v2_5" in config.ELEVENLABS_MODEL:  # seuls ces modèles acceptent de forcer la langue
            body["language_code"] = config.LANGUAGE
        url = f"{ELEVEN_URL}/text-to-speech/{voice_id}?output_format=pcm_{SR}"
        return np.frombuffer(_https(url, config.ELEVENLABS_API_KEY, body), dtype=np.int16)

    def _edge(self, text, voice, rate="+0%", pitch="+0Hz"):
        import edge_tts
        import miniaudio

        async def fetch():
            data = bytearray()
            tts = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            async for chunk in tts.stream():
                if chunk["type"] == "audio":
                    data.extend(chunk["data"])
            return bytes(data)

        mp3 = asyncio.run(fetch())
        dec = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=SR)
        return np.array(dec.samples, dtype=np.int16)

    def _say_offline(self, text):
        import pyttsx3

        if self._offline is None:
            self._offline = pyttsx3.init()
            for v in self._offline.getProperty("voices"):
                if "fr" in (v.id + v.name).lower():
                    self._offline.setProperty("voice", v.id)
                    break
        self._offline.say(text)
        self._offline.runAndWait()
