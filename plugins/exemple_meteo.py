"""Exemple de plugin : la météo (sans clé d'API, via wttr.in).

Pour ajouter une capacité à Jarvis, copie ce modèle dans un nouveau fichier de ce dossier.
Jarvis peut aussi écrire ses propres plugins : demande-lui « crée-toi un outil pour ... ».
"""
import requests

from jarvis.tools import tool


@tool(
    "Donne la météo actuelle et la prévision du jour pour une ville.",
    {"ville": {"type": "string", "description": "Ville, ex : Paris"}},
)
def meteo(ville):
    r = requests.get(f"https://wttr.in/{ville}?format=j1&lang=fr", timeout=10).json()
    now = r["current_condition"][0]
    today = r["weather"][0]
    desc = now.get("lang_fr", now["weatherDesc"])[0]["value"]
    return (
        f"{ville} : {desc}, {now['temp_C']} degrés (ressenti {now['FeelsLikeC']}). "
        f"Aujourd'hui entre {today['mintempC']} et {today['maxtempC']} degrés."
    )
