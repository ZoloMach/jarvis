"""Fenêtre de Jarvis : orbe animée, conversation, saisie au clavier, réglages."""
import math
import os
import platform
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser

import customtkinter as ctk

from . import config, updater

IS_WINDOWS = platform.system() == "Windows"
ICON = config.ROOT / "jarvis.ico"

BG = "#05080f"
PANEL = "#0b1220"
ACCENT = "#00d4ff"
TEXT = "#e6f1ff"
MUTED = "#7a8ba6"
ERROR = "#ff5c6c"

STATE_COLORS = {
    "chargement": "#8a7dff",
    "veille": "#1e8fff",
    "ecoute": "#00e5ff",
    "reflexion": "#ffb020",
    "parle": "#00d4ff",
    "pause": "#4a5568",
    "texte": "#1e8fff",
}
STATE_TEXT = {
    "chargement": "Démarrage...",
    "veille": "Dis « Hey {name} » ou clique sur Parler",
    "ecoute": "Je t'écoute...",
    "reflexion": "Je réfléchis...",
    "parle": "Je parle (dis « Hey {name} » pour me couper)",
    "pause": "Micro coupé",
    "texte": "Écris-moi en bas de la fenêtre",
}
STATE_SPEED = {"chargement": 1.5, "veille": 0.6, "ecoute": 2.5, "reflexion": 7, "parle": 2, "pause": 0, "texte": 0.6}

VOICES = {
    "Henri (homme, France)": "fr-FR-HenriNeural",
    "Rémy (homme, France)": "fr-FR-RemyMultilingualNeural",
    "Denise (femme, France)": "fr-FR-DeniseNeural",
    "Vivienne (femme, France)": "fr-FR-VivienneMultilingualNeural",
    "Antoine (homme, Québec)": "fr-CA-AntoineNeural",
}
MODELS = {
    "Rapide (Claude Sonnet)": "claude-sonnet-5-5",
    "Maximale (Claude Opus, plus lent)": "claude-opus-5-5",
}
BRAINS = {
    "Mon abonnement Claude (Pro ou Max)": "abonnement",
    "Clé API (payée à l'usage)": "api",
}
KEY_URL = "https://console.anthropic.com/settings/keys"
STARTUP_LNK = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup\Jarvis.lnk")


def mix(c1, c2, t):
    """Mélange deux couleurs hex (t=0 -> c1, t=1 -> c2)."""
    a = [int(c1[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def set_icon(win):
    if IS_WINDOWS and ICON.exists():
        # customtkinter remplace l'icône après ~200 ms : on repasse derrière.
        win.after(300, lambda: win.iconbitmap(str(ICON)))


def check_key(key):
    """Renvoie None si la clé fonctionne, sinon un message d'erreur."""
    import anthropic

    try:
        anthropic.Anthropic(api_key=key).models.list(limit=1)
        return None
    except anthropic.AuthenticationError:
        return "Cette clé est refusée par Claude. Vérifie que tu l'as copiée en entier."
    except Exception:  # noqa: BLE001 - pas de réseau : on accepte la clé quand même
        return None


def startup_enabled():
    return IS_WINDOWS and os.path.exists(STARTUP_LNK)


def set_startup(enabled):
    if not IS_WINDOWS:
        return
    if not enabled:
        if os.path.exists(STARTUP_LNK):
            os.remove(STARTUP_LNK)
        return
    pyw = config.ROOT / "Jarvis.pyw"
    ps = (
        f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{STARTUP_LNK}');"
        f"$s.TargetPath='{sys.executable}';$s.Arguments='\"{pyw}\"';"
        f"$s.WorkingDirectory='{config.ROOT}';$s.IconLocation='{ICON}';$s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=0x08000000)  # pas de console


class Dialog(ctk.CTkToplevel):
    def __init__(self, master, title, width=460, height=520):
        super().__init__(master, fg_color=BG)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.resizable(False, False)
        self.transient(master)
        set_icon(self)
        self.after(150, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def label(self, text, size=13, color=TEXT, bold=False, wrap=400, pady=(10, 2)):
        lbl = ctk.CTkLabel(self, text=text, text_color=color, wraplength=wrap, justify="left",
                           font=ctk.CTkFont(size=size, weight="bold" if bold else "normal"))  # fmt: skip
        lbl.pack(anchor="w", padx=24, pady=pady)
        return lbl


class SubscriptionRow(ctk.CTkFrame):
    """État de l'abonnement Claude (via Claude Code) avec un bouton pour l'installer ou le connecter."""

    def __init__(self, master, on_change=None):
        super().__init__(master, fg_color=PANEL, corner_radius=10)
        self.on_change = on_change
        self.status = None
        self.lbl = ctk.CTkLabel(self, text="Vérification de ton abonnement...", text_color=MUTED,
                                wraplength=230, justify="left")  # fmt: skip
        self.lbl.pack(side="left", padx=12, pady=10)
        self.btn = ctk.CTkButton(self, text="...", width=170, state="disabled", command=self.action,
                                 fg_color="#0077a8", hover_color="#0090cc")  # fmt: skip
        self.btn.pack(side="right", padx=12, pady=10)
        self.refresh()

    def _later(self, fn, *args):
        try:
            if self.winfo_exists():
                self.after(0, lambda: fn(*args))
        except (tk.TclError, RuntimeError):
            pass

    def refresh(self, then=None):
        from . import claude_brain

        def work():
            st = claude_brain.auth_status()
            self._later(self._show, st)
            if then:
                then(st)

        threading.Thread(target=work, daemon=True).start()

    def _show(self, st):
        self.status = st
        if st == "connecte":
            self.lbl.configure(text="Abonnement Claude connecté.", text_color=ACCENT)
            self.btn.configure(text="Reconnecter", state="normal", fg_color=PANEL)
        elif st == "deconnecte":
            self.lbl.configure(text="Ton abonnement n'est pas encore connecté.", text_color=TEXT)
            self.btn.configure(text="Connecter mon abonnement", state="normal", fg_color="#0077a8")
        else:
            self.lbl.configure(text="Il manque Claude Code (gratuit avec ton abonnement).", text_color=TEXT)
            self.btn.configure(text="Installer", state="normal", fg_color="#0077a8")
        if self.on_change:
            self.on_change(st)

    def action(self):
        from . import claude_brain

        if self.status == "absent":
            self.btn.configure(state="disabled", text="Installation...")
            self.lbl.configure(text="Installation de Claude Code (une à deux minutes)...", text_color=MUTED)
            threading.Thread(target=lambda: (claude_brain.install(), self.refresh()), daemon=True).start()
            return
        try:
            claude_brain.login()
        except Exception as e:  # noqa: BLE001
            self.lbl.configure(text=str(e), text_color=ERROR)
            return
        self.btn.configure(state="disabled", text="En attente...")
        self.lbl.configure(text="Connecte-toi dans la fenêtre et la page qui viennent de s'ouvrir.", text_color=MUTED)
        deadline = time.time() + 300

        def poll(st=None):
            if st == "connecte" or time.time() > deadline:
                self._later(self._show, st or "deconnecte")
                return
            time.sleep(3)
            self.refresh(then=lambda s: poll(s) if s != "connecte" else None)

        threading.Thread(target=poll, daemon=True).start()


class WelcomeDialog(Dialog):
    """Premier lancement : connecter l'abonnement Claude (ou une clé API) et donner son prénom."""

    def __init__(self, master, on_saved):
        super().__init__(master, "Bienvenue dans Jarvis", height=520)
        self.on_saved = on_saved
        self.mode = "abonnement"
        self.protocol("WM_DELETE_WINDOW", master.quit_app)

        self.label("Bienvenue !", size=22, bold=True, pady=(20, 4))
        self.intro = self.label("Jarvis réfléchit avec ton abonnement Claude (Pro ou Max), sans frais en plus. "
                                "Connecte-le une seule fois :")  # fmt: skip
        self.sub = SubscriptionRow(self, on_change=self._status_changed)
        self.sub.pack(fill="x", padx=24, pady=8)

        self.key_box = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(self.key_box, text="Clé API Claude (payée à l'usage)", text_color=TEXT).pack(anchor="w")
        self.key = ctk.CTkEntry(self.key_box, width=410, show="•", placeholder_text="sk-ant-...")
        self.key.pack(anchor="w", pady=4)
        ctk.CTkButton(self.key_box, text="Obtenir une clé", fg_color="#1f2a3d", hover_color="#2a3a55",
                      command=lambda: webbrowser.open(KEY_URL)).pack(anchor="w")  # fmt: skip

        self.label("Ton prénom")
        self.user = ctk.CTkEntry(self, width=410)
        self.user.pack(padx=24)
        self.user.insert(0, config.USER_NAME)

        self.msg = self.label("", color=ERROR)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=10, side="bottom")
        self.go = ctk.CTkButton(row, text="C'est parti", state="disabled", command=self.save,
                                fg_color="#0077a8", hover_color="#0090cc")  # fmt: skip
        self.go.pack(side="right")
        self.switch_btn = ctk.CTkButton(row, text="Utiliser une clé API", fg_color="transparent",
                                        hover_color="#1a2740", text_color=MUTED, command=self.switch)  # fmt: skip
        self.switch_btn.pack(side="left")

    def _status_changed(self, st):
        if self.mode == "abonnement":
            self.go.configure(state="normal" if st == "connecte" else "disabled")

    def switch(self):
        if self.mode == "abonnement":
            self.mode = "api"
            self.sub.pack_forget()
            self.intro.configure(text="Jarvis utilisera ta clé API Claude (facturée à l'usage, en plus de tout abonnement) :")
            self.key_box.pack(fill="x", padx=24, pady=8, after=self.intro)
            self.switch_btn.configure(text="Utiliser mon abonnement")
            self.go.configure(state="normal")
        else:
            self.mode = "abonnement"
            self.key_box.pack_forget()
            self.intro.configure(text="Jarvis réfléchit avec ton abonnement Claude (Pro ou Max), sans frais en plus. "
                                 "Connecte-le une seule fois :")  # fmt: skip
            self.sub.pack(fill="x", padx=24, pady=8, after=self.intro)
            self.switch_btn.configure(text="Utiliser une clé API")
            self._status_changed(self.sub.status)

    def save(self):
        values = {"JARVIS_USER_NAME": self.user.get().strip() or "Michel", "JARVIS_BRAIN": self.mode,
                  "JARVIS_SETUP_DONE": "1"}  # fmt: skip
        if self.mode == "abonnement":
            self._finish(values, None)
            return
        key = self.key.get().strip()
        if not key.startswith("sk-"):
            self.msg.configure(text="Colle ta clé : elle commence par « sk-ant- ».")
            return
        values["ANTHROPIC_API_KEY"] = key
        self.go.configure(state="disabled", text="Vérification...")

        def work():
            err = check_key(key)
            self.after(0, lambda: self._finish(values, err))

        threading.Thread(target=work, daemon=True).start()

    def _finish(self, values, err):
        if err:
            self.msg.configure(text=err)
            self.go.configure(state="normal", text="C'est parti")
            return
        config.save(**values)
        self.grab_release()
        self.destroy()
        self.on_saved()


class SettingsDialog(Dialog):
    def __init__(self, master, on_saved):
        super().__init__(master, "Réglages de Jarvis", height=640)
        self.on_saved = on_saved
        self.body = ctk.CTkScrollableFrame(self, fg_color=BG)
        self.body.pack(fill="both", expand=True)

        self.label("Cerveau de Jarvis")
        current_brain = next((k for k, v in BRAINS.items() if v == config.BRAIN), list(BRAINS)[0])
        self.brain = ctk.CTkOptionMenu(self.body, values=list(BRAINS), width=400)
        self.brain.set(current_brain)
        self.brain.pack(padx=24, anchor="w")
        SubscriptionRow(self.body).pack(fill="x", padx=24, pady=8)

        self.label("Clé API Claude (seulement pour le mode clé API)")
        self.key = ctk.CTkEntry(self.body, width=400, show="•", placeholder_text="sk-ant-...")
        self.key.pack(padx=24, anchor="w")
        if config.ANTHROPIC_API_KEY:
            self.key.insert(0, config.ANTHROPIC_API_KEY)

        self.label("Ton prénom")
        self.user = ctk.CTkEntry(self.body, width=400)
        self.user.pack(padx=24, anchor="w")
        self.user.insert(0, config.USER_NAME)

        self.label("Voix de Jarvis")
        current_voice = next((k for k, v in VOICES.items() if v == config.TTS_VOICE), list(VOICES)[0])
        self.voice = ctk.CTkOptionMenu(self.body, values=list(VOICES), width=400)
        self.voice.set(current_voice)
        self.voice.pack(padx=24, anchor="w")

        self.label("Intelligence")
        current_model = next((k for k, v in MODELS.items() if v == config.MODEL), list(MODELS)[0])
        self.model = ctk.CTkOptionMenu(self.body, values=list(MODELS), width=400)
        self.model.set(current_model)
        self.model.pack(padx=24, anchor="w")

        self.label("Sensibilité au « Hey Jarvis » (à droite = se réveille plus facilement)")
        self.sens = ctk.CTkSlider(self.body, from_=0.2, to=0.85, width=400)
        self.sens.set(1.05 - config.WAKEWORD_THRESHOLD)
        self.sens.pack(padx=24, pady=4, anchor="w")

        self.label("Mot de passe OBS (Outils > Paramètres du serveur WebSocket)")
        self.obs = ctk.CTkEntry(self.body, width=400, show="•")
        self.obs.pack(padx=24, anchor="w")
        if config.OBS_PASSWORD:
            self.obs.insert(0, config.OBS_PASSWORD)

        self.startup = ctk.CTkSwitch(self.body, text="Lancer Jarvis au démarrage de Windows", text_color=TEXT)
        if startup_enabled():
            self.startup.select()
        self.startup.pack(anchor="w", padx=24, pady=(14, 4))

        self.auto_update = ctk.CTkSwitch(self.body, text="Mises à jour automatiques", text_color=TEXT)
        if config.AUTO_UPDATE:
            self.auto_update.select()
        self.auto_update.pack(anchor="w", padx=24, pady=(10, 4))
        upd = ctk.CTkFrame(self.body, fg_color="transparent")
        upd.pack(fill="x", padx=24, pady=(2, 8))
        self.update_msg = ctk.CTkLabel(upd, text=f"Version {updater.current_version()}", text_color=MUTED)
        self.update_msg.pack(side="left")
        self.update_btn = ctk.CTkButton(upd, text="Rechercher une mise à jour", width=190, fg_color="#1f2a3d",
                                        hover_color="#2a3a55", command=self.check_update)  # fmt: skip
        self.update_btn.pack(side="right")

        self.msg = ctk.CTkLabel(self, text="", text_color=ERROR, wraplength=400)
        self.msg.pack(padx=24)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=10)
        self.save_btn = ctk.CTkButton(row, text="Enregistrer", command=self.save,
                                      fg_color="#0077a8", hover_color="#0090cc")  # fmt: skip
        self.save_btn.pack(side="right")
        ctk.CTkButton(row, text="Dossier de Jarvis", fg_color="#1f2a3d", hover_color="#2a3a55",
                      command=self.open_folder).pack(side="left")  # fmt: skip

    def label(self, text, **kw):
        lbl = ctk.CTkLabel(self.body, text=text, text_color=kw.get("color", TEXT), wraplength=400, justify="left")
        lbl.pack(anchor="w", padx=24, pady=(10, 2))
        return lbl

    def open_folder(self):
        if IS_WINDOWS:
            os.startfile(config.ROOT)  # noqa: S606

    def check_update(self):
        self.update_btn.configure(state="disabled", text="Recherche...")

        def work():
            version = updater.available(timeout=10)
            self.after(0, lambda: self._update_checked(version))

        threading.Thread(target=work, daemon=True).start()

    def _update_checked(self, version):
        if not self.winfo_exists():
            return
        self.update_btn.configure(state="normal", text="Rechercher une mise à jour")
        if version:
            self.update_msg.configure(text=f"Version {version} disponible", text_color=ACCENT)
            self.master.events.put(("update", version))
        else:
            self.update_msg.configure(text=f"Version {updater.current_version()} : Jarvis est à jour")

    def save(self):
        brain = BRAINS[self.brain.get()]
        key = self.key.get().strip()
        if brain == "api" and not key.startswith("sk-"):
            self.msg.configure(text="Pour le mode clé API, colle ta clé : elle commence par « sk-ant- ».")
            return
        self.save_btn.configure(state="disabled", text="Vérification...")
        self.msg.configure(text="")

        def work():
            err = check_key(key) if brain == "api" and key != config.ANTHROPIC_API_KEY else None
            self.after(0, lambda: self._finish(brain, key, err))

        threading.Thread(target=work, daemon=True).start()

    def _finish(self, brain, key, err):
        if err:
            self.msg.configure(text=err)
            self.save_btn.configure(state="normal", text="Enregistrer")
            return
        changed = brain != config.BRAIN
        values = dict(
            JARVIS_BRAIN=brain,
            JARVIS_USER_NAME=self.user.get().strip() or "Michel",
            JARVIS_VOICE=VOICES[self.voice.get()],
            JARVIS_MODEL=MODELS[self.model.get()],
            JARVIS_WAKEWORD_THRESHOLD=f"{1.05 - self.sens.get():.2f}",
            OBS_PASSWORD=self.obs.get(),
            JARVIS_SETUP_DONE="1",
            JARVIS_AUTO_UPDATE="1" if self.auto_update.get() else "0",
        )
        if key:
            values["ANTHROPIC_API_KEY"] = key
        try:
            set_startup(bool(self.startup.get()))
        except Exception as e:  # noqa: BLE001
            print(f"[réglages] démarrage auto : {e}")
        config.save(**values)
        self.grab_release()
        self.destroy()
        self.on_saved(changed)


class ConfirmDialog(Dialog):
    def __init__(self, master, action, details, holder):
        super().__init__(master, "Confirmation", height=300)
        self.holder = holder
        self.label(f"Jarvis voudrait {action}.", bold=True, size=15, pady=(18, 4))
        box = ctk.CTkTextbox(self, height=90, fg_color=PANEL, text_color=ACCENT, wrap="word")
        box.insert("end", details)
        box.configure(state="disabled")
        box.pack(fill="x", padx=24, pady=6)
        self.label("Tu peux aussi répondre « oui » ou « non » à voix haute.", color=MUTED, size=12)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=12)
        ctk.CTkButton(row, text="Oui, vas-y", command=lambda: self.answer(True),
                      fg_color="#0077a8", hover_color="#0090cc").pack(side="right")  # fmt: skip
        ctk.CTkButton(row, text="Non", command=lambda: self.answer(False),
                      fg_color="#3a1f28", hover_color="#552a38").pack(side="right", padx=8)  # fmt: skip
        self.protocol("WM_DELETE_WINDOW", lambda: self.answer(False))
        self._poll()

    def answer(self, ok):
        if not self.holder["event"].is_set():
            self.holder["ok"] = ok
            self.holder["event"].set()
        self.destroy()

    def _poll(self):
        # Répondu à la voix : on ferme la fenêtre.
        if self.holder["event"].is_set():
            self.destroy()
        else:
            self.after(200, self._poll)


class App(ctk.CTk):
    def __init__(self, news=None):
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=BG)
        self.title(config.NAME.upper())
        self.geometry("480x760")
        self.minsize(400, 600)
        set_icon(self)
        self.events: queue.Queue = queue.Queue()
        self.engine = None
        self.state_name = "chargement"
        self.angle = 0.0
        self.level = 0.0
        self.t0 = time.time()
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.quit_app)
        self.after(33, self._animate)
        self.after(50, self._pump)
        if news:
            self.write("info", f"Jarvis vient d'être mis à jour (version {news[0]}).\n{news[1]}".strip())
        threading.Thread(target=self._watch_updates, daemon=True).start()
        if config.SETUP_DONE or (config.BRAIN == "api" and config.ANTHROPIC_API_KEY):
            self.after(100, self.start_engine)
        else:
            self.after(400, lambda: WelcomeDialog(self, self.start_engine))

    # --- Construction de la fenêtre ---
    def _build(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(14, 0))
        ctk.CTkLabel(head, text=" ".join(config.NAME.upper()), text_color=ACCENT,
                     font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")  # fmt: skip
        ctk.CTkButton(head, text="Réglages", width=90, fg_color=PANEL, hover_color="#1a2740",
                      command=self.open_settings).pack(side="right")  # fmt: skip
        ctk.CTkButton(head, text="Journal", width=80, fg_color=PANEL, hover_color="#1a2740",
                      command=self.copy_log).pack(side="right", padx=(0, 8))  # fmt: skip
        # Apparaît quand une nouvelle version est publiée pendant que Jarvis tourne.
        self.update_btn = ctk.CTkButton(head, text="Mettre à jour", width=110, fg_color="#0077a8",
                                        hover_color="#0090cc", command=self.restart_for_update)  # fmt: skip

        self.canvas = tk.Canvas(self, width=260, height=260, bg=BG, highlightthickness=0)
        self.canvas.pack(pady=(6, 0))
        self.status = ctk.CTkLabel(self, text="", text_color=MUTED, font=ctk.CTkFont(size=14))
        self.status.pack(pady=(0, 8))

        self.log = ctk.CTkTextbox(self, fg_color=PANEL, text_color=TEXT, wrap="word",
                                  font=ctk.CTkFont(size=13), corner_radius=12)  # fmt: skip
        self.log.pack(fill="both", expand=True, padx=18)
        self.log.tag_config("user", foreground="#ffffff")
        self.log.tag_config("jarvis", foreground=ACCENT)
        self.log.tag_config("tool", foreground=MUTED)
        self.log.tag_config("info", foreground=MUTED)
        self.log.tag_config("error", foreground=ERROR)
        self.log.configure(state="disabled")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=18, pady=(10, 4))
        self.mic_btn = ctk.CTkButton(bar, text="Micro : activé", width=120, fg_color=PANEL,
                                     hover_color="#1a2740", command=self.toggle_mic)  # fmt: skip
        self.mic_btn.pack(side="left")
        ctk.CTkButton(bar, text="Parler", width=120, fg_color="#0077a8", hover_color="#0090cc",
                      command=self.push_to_talk).pack(side="right")  # fmt: skip
        ctk.CTkButton(bar, text="Arrêter", width=90, fg_color="#3a1f28", hover_color="#552a38",
                      command=self.stop).pack(side="right", padx=8)  # fmt: skip

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(4, 16))
        self.entry = ctk.CTkEntry(row, placeholder_text="Écris à Jarvis...", height=36)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.send())
        ctk.CTkButton(row, text="Envoyer", width=90, height=36, command=self.send).pack(side="right", padx=(8, 0))

    # --- Actions ---
    def start_engine(self):
        from .engine import Engine

        if self.engine is None:
            self.engine = Engine(lambda kind, data=None: self.events.put((kind, data)))
            self.engine.start()

    def open_settings(self):
        SettingsDialog(self, self._settings_saved)

    def _settings_saved(self, brain_changed):
        self.write("info", "Réglages enregistrés.")
        if brain_changed and self.engine:
            threading.Thread(target=self._reload_brain, daemon=True).start()

    def _reload_brain(self):
        try:
            self.engine.load_brain()
            self.events.put(("info", "Cerveau de Jarvis changé."))
        except Exception as e:  # noqa: BLE001
            self.events.put(("error", str(e)))

    def send(self):
        text = self.entry.get().strip()
        if text and self.engine:
            self.entry.delete(0, "end")
            self.engine.send_text(text)

    def push_to_talk(self):
        if self.engine and self.engine.ears:
            if not self.engine.mic_enabled:
                self.toggle_mic()
            self.engine.push_to_talk()

    def toggle_mic(self):
        if not self.engine:
            return
        on = not self.engine.mic_enabled
        self.engine.set_mic(on)
        self.mic_btn.configure(text="Micro : activé" if on else "Micro : coupé")

    def stop(self):
        if self.engine:
            self.engine.cancel()

    def copy_log(self):
        """Copie la fin du journal dans le presse-papiers (pour l'envoyer à Claude) et l'ouvre."""
        path = config.DATA_DIR / "jarvis.log"
        if not path.exists():
            self.write("info", "Le journal est vide pour l'instant.")
            return
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-150:]
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.write("info", "Les dernières lignes du journal sont copiées : colle-les dans ta conversation avec Claude.")
        if IS_WINDOWS:
            os.startfile(path)  # noqa: S606

    def _watch_updates(self):
        """Jarvis peut rester ouvert des jours : on regarde toutes les 6 heures si une nouvelle version existe."""
        while True:
            time.sleep(6 * 3600)
            version = updater.available() if updater.enabled() else None
            if version:
                self.events.put(("update", version))
                return

    def show_update(self, version):
        if not self.update_btn.winfo_ismapped():
            self.update_btn.pack(side="right", padx=(0, 8))
            self.write("info", f"La version {version} de Jarvis est prête : clique sur « Mettre à jour » "
                               "(Jarvis redémarre quelques secondes).")  # fmt: skip

    def restart_for_update(self):
        """Relance Jarvis : la nouvelle version s'installe au démarrage."""
        if not updater.installed():
            self.write("info", "Cette copie de Jarvis n'a pas été posée par l'installeur : mets-la à jour avec git.")
            return
        updater.restart("--maj")
        self.quit_app()

    def quit_app(self):
        self.destroy()
        os._exit(0)

    # --- Événements venant du moteur ---
    def write(self, tag, text):
        prefix = {"user": "Toi : ", "jarvis": f"{config.NAME} : ", "tool": "    > ", "info": "", "error": "! "}[tag]
        self.log.configure(state="normal")
        self.log.insert("end", prefix + text + "\n", tag)
        if tag in ("jarvis", "info", "error"):
            self.log.insert("end", "\n")
        self.log.configure(state="disabled")
        self.log.see("end")

    def _pump(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "state":
                    self.state_name = data
                elif kind == "confirm":
                    ConfirmDialog(self, *data)
                elif kind == "update":
                    self.show_update(data)
                elif kind == "tool":
                    self.write("tool", data.replace("_", " "))
                else:
                    self.write(kind, data)
        except queue.Empty:
            pass
        self.after(50, self._pump)

    # --- Animation de l'orbe ---
    def _animate(self):
        state = "parle" if self.engine and self.engine.speaking else self.state_name
        t = time.time() - self.t0
        color = STATE_COLORS.get(state, ACCENT)
        target = self.engine.mic_level if (self.engine and state == "ecoute") else 0.0
        self.level += (target - self.level) * 0.3
        if state == "parle":
            pulse = 6 + 6 * math.sin(t * 9) * math.sin(t * 2.3)
        elif state == "ecoute":
            pulse = 4 + self.level * 34
        elif state == "pause":
            pulse = 0
        else:
            pulse = 3 * math.sin(t * 2)
        self.angle = (self.angle + STATE_SPEED.get(state, 1)) % 360
        if state != getattr(self, "_shown_state", None):
            self._shown_state, self._state_since = state, time.time()
        status = STATE_TEXT.get(state, "").format(name=config.NAME)
        waited = time.time() - self._state_since
        if state == "reflexion" and waited > 3:
            status += f" ({waited:.0f} s)"
        self.status.configure(text=status)

        c, cx, cy = self.canvas, 130, 130
        c.delete("all")
        for r, k in ((122, 0.12), (112, 0.08)):
            c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=mix(BG, color, k + 0.1), width=1)
        for i in range(3):
            c.create_arc(cx - 104, cy - 104, cx + 104, cy + 104, start=self.angle + i * 120, extent=70,
                         style="arc", outline=mix(BG, color, 0.85), width=5)  # fmt: skip
        for i in range(4):
            c.create_arc(cx - 86, cy - 86, cx + 86, cy + 86, start=-self.angle * 1.4 + i * 90, extent=45,
                         style="arc", outline=mix(BG, color, 0.5), width=3)  # fmt: skip
        for i in range(24):
            a = math.radians(i * 15 + self.angle * 0.3)
            r1, r2 = 70, 74 if i % 2 else 78
            c.create_line(cx + r1 * math.cos(a), cy + r1 * math.sin(a), cx + r2 * math.cos(a), cy + r2 * math.sin(a),
                          fill=mix(BG, color, 0.35), width=2)  # fmt: skip
        core = 40 + pulse
        for k, extra in ((0.15, 22), (0.3, 12), (0.55, 5)):
            r = core + extra
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=mix(BG, color, k), outline="")
        c.create_oval(cx - core, cy - core, cx + core, cy + core, fill=mix(color, "#ffffff", 0.35), outline=color, width=2)
        r = core * 0.45
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=mix(color, "#ffffff", 0.8), outline="")
        self.after(33, self._animate)


def main(news=None):
    app = App(news)
    app.mainloop()


if __name__ == "__main__":
    main()
