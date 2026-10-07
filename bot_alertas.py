import os
import json
import time
import re
import unicodedata
import feedparser
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
HISTORIAL_FILE = "enlaces_vistos.json"
RSS_FILE = "rss_urls.txt"

# 1. PALABRAS QUE DESCARTAN LA NOTICIA AUTOMÁTICAMENTE
PALABRAS_EXCLUIDAS = [
    "fotograf", "deport", "fútbol", "futbol", "poesía", "poesia", "teatro",
    "salud mental", "accidente", "policial", "violencia", "música", "musica",
    "literario", "escultura", "danza", "legislativo", "carnaval", "farándula",
    "espectáculo", "vecinal", "tránsito", "homicidio", "robo", "hurto"
]

# 2. PALABRAS QUE LA NOTICIA DEBE TENER SÍ O SÍ
PALABRAS_INCLUSION = [
    "ingenieria", "ingeniería", "electronica", "electrónica", "sistemas",
    "software", "programacion", "programación", "hardware", "embebido",
    "embebidos", "iot", "telecomunicaciones", "ciberseguridad", "inteligencia artificial",
    "datos", "utn", "facet", "copit", "sidetec", "ieee", "balseiro",
    "conae", "invap", "pasantia", "pasantía", "pps", "practica supervisada",
    "práctica supervisada", "beca", "becas", "hackathon", "robotica", "robótica"
]

def normalizar_texto(texto):
    """Convierte a minúsculas, elimina acentos y caracteres especiales."""
    texto = texto.lower()
    texto = unicodedata.normalize('NFD', texto).encode('ascii', 'ignore').decode('utf-8')
    texto = re.sub(r'[^a-z0-9]', '', texto)
    return texto

def cargar_historial():
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def guardar_historial(vistos):
    with open(HISTORIAL_FILE, "w", encoding="utf-8") as f:
        json.dump(list(vistos), f, ensure_ascii=False, indent=2)

def es_noticia_valida(titulo, resumen):
    texto_completo = f"{titulo} {resumen}".lower()

    if any(palabra in texto_completo for palabra in PALABRAS_EXCLUIDAS):
        return False

    if any(palabra in texto_completo for palabra in PALABRAS_INCLUSION):
        return True

    return False

def enviar_telegram(titulo, resumen, link):
    mensaje = f"🔔 *NUEVA NOTICIA DETECTADA*\n\n📌 *{titulo}*\n\n📝 {resumen}\n\n🔗 {link}"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error al enviar a Telegram: {e}")

def main():
    if not os.path.exists(RSS_FILE):
        print("No se encontró el archivo rss_urls.txt")
        return

    with open(RSS_FILE, "r", encoding="utf-8") as f:
        rss_urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    vistos = cargar_historial()
    enviadas = 0

    for rss_url in rss_urls:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                link = entry.link
                titulo = entry.title.replace("*", "")
                resumen = entry.get("summary", "").replace("<b>", "").replace("</b>", "").replace("*", "")

                titulo_norm = normalizar_texto(titulo)

                # Si ya vimos el enlace O el título normalizado, saltamos la noticia
                if link in vistos or (titulo_norm and titulo_norm in vistos):
                    continue

                # Guardamos enlace y título en el historial para evitar futuras repeticiones
                vistos.add(link)
                if titulo_norm:
                    vistos.add(titulo_norm)

                if es_noticia_valida(titulo, resumen):
                    enviar_telegram(titulo, resumen, link)
                    enviadas += 1
                    time.sleep(1)
        except Exception as e:
            print(f"Error procesando {rss_url}: {e}")

    guardar_historial(vistos)
    print(f"Proceso finalizado. Alertas enviadas a Telegram: {enviadas}")

if __name__ == "__main__":
    main()
