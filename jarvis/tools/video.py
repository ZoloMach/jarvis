"""Montage vidéo avec FFmpeg : couper, assembler, accélérer, format vertical, retirer les blancs..."""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from .. import config
from . import tool


def _p(path):
    return Path(os.path.expandvars(os.path.expanduser(path))).resolve()


def _out(src, suffix, sortie=None):
    if sortie:
        return _p(sortie)
    s = _p(src)
    return s.with_name(f"{s.stem}_{suffix}{s.suffix}")


def _ffmpeg(*args):
    cmd = [config.FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *map(str, args)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-1500:])


def _duration(path):
    ffprobe = str(Path(config.FFMPEG).with_name("ffprobe")) if os.sep in config.FFMPEG else "ffprobe"
    r = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        text=True,
    )
    return json.loads(r.stdout)


@tool("Donne les infos d'une vidéo (durée, résolution, fps).", {"fichier": {"type": "string"}})
def video_infos(fichier):
    info = _duration(_p(fichier))
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), {})
    return (
        f"Durée : {float(info['format']['duration']):.1f} s, résolution : {v.get('width')}x{v.get('height')}, "
        f"fps : {v.get('r_frame_rate')}, taille : {int(info['format']['size']) / 1e6:.1f} Mo."
    )


@tool(
    "Découpe un extrait d'une vidéo. Temps au format secondes ou HH:MM:SS.",
    {"fichier": {"type": "string"}, "debut": {"type": "string"}, "fin": {"type": "string"}, "sortie": {"type": "string"}},
)
def video_couper(fichier, debut, fin, sortie=None):
    out = _out(fichier, "extrait", sortie)
    _ffmpeg("-ss", debut, "-to", fin, "-i", _p(fichier), "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac", out)
    return f"Extrait créé : {out}"


@tool(
    "Assemble plusieurs vidéos bout à bout (même format conseillé).",
    {"fichiers": {"type": "array", "items": {"type": "string"}}, "sortie": {"type": "string"}},
)
def video_assembler(fichiers, sortie):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for v in fichiers:
            f.write(f"file '{_p(v).as_posix()}'\n")
        lst = f.name
    out = _p(sortie)
    try:
        _ffmpeg("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out)
    except RuntimeError:
        _ffmpeg("-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-crf", "20", "-c:a", "aac", out)
    finally:
        os.unlink(lst)
    return f"Montage créé : {out}"


@tool(
    "Recadre une vidéo en format vertical 9:16 (TikTok, Shorts, Reels), centré.",
    {"fichier": {"type": "string"}, "sortie": {"type": "string"}},
)
def video_vertical(fichier, sortie=None):
    out = _out(fichier, "vertical", sortie)
    _ffmpeg("-i", _p(fichier), "-vf", "crop=ih*9/16:ih,scale=1080:1920", "-c:v", "libx264", "-crf", "20", "-c:a", "copy", out)
    return f"Version verticale : {out}"


@tool(
    "Change la vitesse d'une vidéo (ex : 2 = deux fois plus vite, 0.5 = ralenti).",
    {"fichier": {"type": "string"}, "facteur": {"type": "number"}, "sortie": {"type": "string"}},
)
def video_vitesse(fichier, facteur, sortie=None):
    out = _out(fichier, f"x{facteur}", sortie)
    atempo = []
    f = facteur
    while f > 2:
        atempo.append("atempo=2.0")
        f /= 2
    while f < 0.5:
        atempo.append("atempo=0.5")
        f /= 0.5
    atempo.append(f"atempo={f}")
    _ffmpeg("-i", _p(fichier), "-filter:v", f"setpts=PTS/{facteur}", "-filter:a", ",".join(atempo), out)
    return f"Vidéo à vitesse x{facteur} : {out}"


@tool(
    "Ajoute une musique de fond sous une vidéo (volume de la musique entre 0 et 1).",
    {"fichier": {"type": "string"}, "musique": {"type": "string"}, "volume_musique": {"type": "number"}, "sortie": {"type": "string"}},
)
def video_ajouter_musique(fichier, musique, volume_musique=0.2, sortie=None):
    out = _out(fichier, "musique", sortie)
    _ffmpeg(
        "-i", _p(fichier), "-stream_loop", "-1", "-i", _p(musique),
        "-filter_complex", f"[1:a]volume={volume_musique}[m];[0:a][m]amix=inputs=2:duration=first[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", out,
    )  # fmt: skip
    return f"Musique ajoutée : {out}"


@tool(
    "Extrait l'audio d'une vidéo en MP3.",
    {"fichier": {"type": "string"}, "sortie": {"type": "string"}},
)
def video_extraire_audio(fichier, sortie=None):
    out = _p(sortie) if sortie else _p(fichier).with_suffix(".mp3")
    _ffmpeg("-i", _p(fichier), "-vn", "-q:a", "2", out)
    return f"Audio extrait : {out}"


@tool(
    "Compresse une vidéo pour l'envoyer (Discord, mail). Qualité : 'forte' compression ou 'moyenne'.",
    {"fichier": {"type": "string"}, "qualite": {"type": "string", "enum": ["forte", "moyenne"]}, "sortie": {"type": "string"}},
)
def video_compresser(fichier, qualite="moyenne", sortie=None):
    out = _out(fichier, "compresse", sortie)
    crf = "32" if qualite == "forte" else "26"
    _ffmpeg("-i", _p(fichier), "-vf", "scale=-2:'min(1080,ih)'", "-c:v", "libx264", "-crf", crf, "-preset", "medium", "-c:a", "aac", "-b:a", "128k", out)
    return f"Vidéo compressée : {out}"


@tool(
    "Montage automatique : supprime les passages silencieux (blancs, hésitations) d'une vidéo face caméra ou d'un enregistrement.",
    {
        "fichier": {"type": "string"},
        "seuil_db": {"type": "number", "description": "Niveau en dessous duquel c'est du silence, défaut -35"},
        "duree_min": {"type": "number", "description": "Durée minimale d'un silence à couper, défaut 0.6 s"},
        "sortie": {"type": "string"},
    },
)
def video_supprimer_silences(fichier, seuil_db=-35, duree_min=0.6, sortie=None):
    src = _p(fichier)
    r = subprocess.run(
        [config.FFMPEG, "-hide_banner", "-i", str(src), "-af", f"silencedetect=n={seuil_db}dB:d={duree_min}", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )  # fmt: skip
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    total = float(_duration(src)["format"]["duration"])
    if not starts:
        return "Aucun silence détecté, rien à couper."
    # Segments à garder = entre les silences (on laisse 0,15 s de marge pour ne pas couper les mots).
    keep, cursor, pad = [], 0.0, 0.15
    for s, e in zip(starts, ends + [total] * (len(starts) - len(ends))):
        if s - cursor > 0.1:
            keep.append((max(0, cursor - pad), s + pad))
        cursor = e
    if total - cursor > 0.1:
        keep.append((max(0, cursor - pad), total))
    sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in keep)
    out = _out(fichier, "sans_blancs", sortie)
    _ffmpeg(
        "-i", src, "-vf", f"select='{sel}',setpts=N/FRAME_RATE/TB", "-af", f"aselect='{sel}',asetpts=N/SR/TB",
        "-c:v", "libx264", "-crf", "20", "-c:a", "aac", out,
    )  # fmt: skip
    gagne = total - sum(b - a for a, b in keep)
    return f"{len(starts)} blancs supprimés, {gagne:.0f} s gagnées. Fichier : {out}"
