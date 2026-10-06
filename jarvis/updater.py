"""Mise à jour automatique de Jarvis depuis son dépôt GitHub.

Au lancement, Jarvis compare son fichier VERSION à celui du dépôt. Si une version plus récente est publiée, il la
télécharge, installe les éventuelles nouvelles bibliothèques, remplace son code puis redémarre. Les réglages (.env),
la mémoire (data/) et les outils créés par l'utilisateur (plugins/) ne sont jamais touchés. La version précédente
est gardée dans data/version-precedente : si la nouvelle ne démarre pas, Jarvis y revient tout seul.
"""
import datetime
import json
import os
import platform
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path

from . import config

ROOT = config.ROOT
BACKUP = config.DATA_DIR / "version-precedente"
STATE_FILE = config.DATA_DIR / "mise-a-jour.json"
BRANCH = "main"
RAW_URL = "https://raw.githubusercontent.com/{repo}/{branch}/VERSION"
ZIP_URL = "https://codeload.github.com/{repo}/zip/refs/heads/{branch}"
IS_WINDOWS = platform.system() == "Windows"
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0
UNINST_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Jarvis"

# Ce que la mise à jour remplace : chemin dans le dépôt -> chemin dans le dossier de Jarvis.
MANAGED = {
    "jarvis": "jarvis",
    "Jarvis.pyw": "Jarvis.pyw",
    "VERSION": "VERSION",
    "NOUVEAUTES.md": "NOUVEAUTES.md",
    "README.md": "README.md",
    "jarvis.ico": "jarvis.ico",
    ".env.example": ".env.example",
    "installeur/requirements-windows.txt": "requirements-windows.txt",
}


def log(msg):
    print(f"[mise à jour] {msg}", flush=True)


def parse(version):
    try:
        return tuple(int(x) for x in version.strip().split("."))
    except (AttributeError, ValueError):
        return (0,)


def current_version():
    path = ROOT / "VERSION"
    return path.read_text(encoding="utf-8").strip() if path.exists() else "0"


def installed():
    """Vrai pour une copie posée par l'installeur (un dossier de développement se met à jour avec git)."""
    return (ROOT / "uv.exe").exists()


def enabled():
    return config.AUTO_UPDATE and bool(config.UPDATE_REPO) and installed()


def _state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(**values):
    STATE_FILE.write_text(json.dumps(_state() | values, ensure_ascii=False, indent=1), encoding="utf-8")


def _get(url, timeout):
    ctx = ssl.create_default_context()
    try:  # certificats de Windows + ceux de certifi, au cas où Windows n'en aurait pas un à jour
        import certifi

        ctx.load_verify_locations(certifi.where())
    except Exception:  # noqa: BLE001
        pass
    req = urllib.request.Request(url, headers={"User-Agent": "Jarvis", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:  # noqa: S310 - adresse https fixe
        return r.read()


def available(timeout=4):
    """Numéro de la version publiée si elle est plus récente que celle installée, sinon None."""
    try:
        remote = _get(RAW_URL.format(repo=config.UPDATE_REPO, branch=BRANCH), timeout).decode().strip()
    except Exception as e:  # noqa: BLE001 - pas d'Internet : on réessaiera au prochain lancement
        log(f"vérification impossible ({e})")
        return None
    if parse(remote) > parse(current_version()) and remote != _state().get("ignorer"):
        return remote
    return None


# --- Installation ---
def _download(workdir):
    """Télécharge le code du dépôt, vérifie qu'il est complet et lisible, et renvoie le dossier extrait."""
    archive = workdir / "jarvis.zip"
    archive.write_bytes(_get(ZIP_URL.format(repo=config.UPDATE_REPO, branch=BRANCH), timeout=120))
    with zipfile.ZipFile(archive) as z:
        z.extractall(workdir / "code")
    tops = [p for p in (workdir / "code").iterdir() if p.is_dir()]
    if len(tops) != 1:
        raise RuntimeError("archive inattendue")
    src = tops[0]
    for needed in ("VERSION", "Jarvis.pyw", "jarvis/__init__.py", "jarvis/gui.py", "jarvis/updater.py"):
        if not (src / needed).exists():
            raise RuntimeError(f"fichier manquant dans la nouvelle version : {needed}")
    # Une faute de frappe dans le code publié ne doit pas casser Jarvis : tout doit se lire avant d'installer.
    for py in [src / "Jarvis.pyw", *(src / "jarvis").rglob("*.py")]:
        compile(py.read_text(encoding="utf-8"), str(py), "exec")
    return src


def _install_requirements(src):
    """Installe les bibliothèques ajoutées ou changées par la nouvelle version (avec uv, comme l'installeur)."""
    new = src / "installeur" / "requirements-windows.txt"
    old = ROOT / "requirements-windows.txt"
    if not new.exists() or (old.exists() and old.read_bytes() == new.read_bytes()):
        return
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    python = venv_python if venv_python.exists() else Path(sys.executable)
    env = os.environ | {
        "UV_CACHE_DIR": str(ROOT / "cache"),
        "UV_PYTHON_INSTALL_DIR": str(ROOT / "python"),
        "UV_PYTHON_PREFERENCE": "only-managed",
        "UV_LINK_MODE": "copy",
        "UV_NO_PROGRESS": "1",
        "NO_COLOR": "1",
    }
    log("installation des nouvelles bibliothèques...")
    r = subprocess.run([str(ROOT / "uv.exe"), "pip", "install", "--python", str(python), "-r", str(new)],
                       env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=1800, creationflags=NO_WINDOW)  # fmt: skip
    shutil.rmtree(ROOT / "cache", ignore_errors=True)
    if r.returncode != 0:
        raise RuntimeError(f"installation des bibliothèques impossible : {(r.stdout + r.stderr)[-800:]}")


def _remove(path):
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _copy(src, dst):
    if src.is_dir():
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _restore_backup():
    for dst in MANAGED.values():
        if (BACKUP / dst).exists():
            _remove(ROOT / dst)
            _copy(BACKUP / dst, ROOT / dst)


def _set_registry_version(version):
    """Met à jour la version affichée dans « Applications installées » de Windows."""
    if not IS_WINDOWS:
        return
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINST_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, version)
    except OSError:
        pass


def update(version, progress=lambda text: None):
    """Télécharge et installe la version publiée. Renvoie None si tout s'est bien passé, sinon l'erreur."""
    old = current_version()
    with tempfile.TemporaryDirectory(prefix="jarvis-maj-") as tmp:
        try:
            progress(f"Téléchargement de la version {version}...")
            src = _download(Path(tmp))
            progress("Installation des nouveaux composants...")
            _install_requirements(src)
            progress("Remplacement des fichiers...")
            shutil.rmtree(BACKUP, ignore_errors=True)
            for dst in MANAGED.values():
                if (ROOT / dst).exists():
                    _copy(ROOT / dst, BACKUP / dst)
        except Exception as e:  # noqa: BLE001
            log(f"abandon, rien n'a été changé : {e}")
            return str(e)
        try:
            for repo_path, dst in MANAGED.items():
                if (src / repo_path).exists():
                    _remove(ROOT / dst)
                    _copy(src / repo_path, ROOT / dst)
            # Les exemples fournis sont mis à jour ; les outils créés par l'utilisateur restent en place.
            for plugin in (src / "plugins").glob("*.py"):
                shutil.copy2(plugin, config.PLUGINS_DIR / plugin.name)
        except Exception as e:  # noqa: BLE001 - fichier bloqué par un antivirus, disque plein...
            log(f"échec du remplacement ({e}), retour à la version {old}")
            _restore_backup()
            return str(e)
    new = current_version()
    _save_state(precedente=old, installee=new, date=datetime.datetime.now().isoformat(timespec="seconds"),
                a_annoncer=True)  # fmt: skip
    _set_registry_version(new)
    log(f"version {old} -> {new} installée")
    return None


def rollback():
    """Remet la version précédente si la nouvelle ne démarre pas. Renvoie True si c'est fait."""
    if not BACKUP.exists():
        return False
    bad = current_version()
    _restore_backup()
    _save_state(ignorer=bad, a_annoncer=False)
    _set_registry_version(current_version())
    log(f"la version {bad} ne démarre pas : retour à la version {current_version()}")
    return True


def restart(*args):
    """Relance Jarvis dans un nouveau processus (l'appelant se ferme ensuite)."""
    subprocess.Popen([sys.executable, str(ROOT / "Jarvis.pyw"), *args], cwd=ROOT, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)  # fmt: skip


def at_startup(force=False):
    """Appelée par Jarvis.pyw avant d'ouvrir la fenêtre. True si une version vient d'être installée (redémarrer).

    `force` : l'utilisateur a cliqué sur « Mettre à jour », même si les mises à jour automatiques sont coupées.
    """
    if not (enabled() or (force and installed())):
        return False
    version = available()
    return bool(version) and _update_with_window(version) is None


def _update_with_window(version):
    """Installe la mise à jour en affichant une petite fenêtre de progression."""
    import tkinter as tk

    try:
        win = tk.Tk()
    except tk.TclError:
        return update(version)
    win.title("Jarvis")
    win.configure(bg="#05080f")
    win.geometry("420x120")
    win.resizable(False, False)
    win.protocol("WM_DELETE_WINDOW", lambda: None)  # on ne ferme pas en plein remplacement des fichiers
    if IS_WINDOWS and (ROOT / "jarvis.ico").exists():
        win.iconbitmap(str(ROOT / "jarvis.ico"))
    tk.Label(win, text=f"Mise à jour de Jarvis ({current_version()} → {version})", fg="#00d4ff", bg="#05080f",
             font=("Segoe UI", 12, "bold")).pack(pady=(26, 4))  # fmt: skip
    label = tk.Label(win, text="", fg="#7a8ba6", bg="#05080f", font=("Segoe UI", 10))
    label.pack()
    win.eval("tk::PlaceWindow . center")
    status = {"text": "Préparation...", "done": False}

    def work():
        status["error"] = update(version, progress=lambda text: status.update(text=text))
        status["done"] = True

    def poll():
        label.configure(text=status["text"])
        if status["done"]:
            win.destroy()
        else:
            win.after(150, poll)

    threading.Thread(target=work, daemon=True).start()
    poll()
    win.mainloop()
    return status.get("error")


def news():
    """Juste après une mise à jour (une seule fois) : (version, texte des nouveautés). Sinon None."""
    st = _state()
    if not st.get("a_annoncer"):
        return None
    _save_state(a_annoncer=False)
    version = current_version()
    lines, inside = [], False
    path = ROOT / "NOUVEAUTES.md"
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        if line.startswith("## "):
            inside = line[3:].strip() == version
        elif inside and line.strip():
            lines.append(line.strip())
    return version, "\n".join(lines)
