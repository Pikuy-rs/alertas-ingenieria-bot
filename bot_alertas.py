import os
import json
import time
import feedparser
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
HISTORIAL_FILE = "enlaces_vistos.json"
RSS_FILE = "rss_urls.txt"

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
    nuevos = 0

    for rss_url in rss_urls:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                link = entry.link
                if link not in vistos:
                    titulo = entry.title.replace("*", "")
                    resumen = entry.get("summary", "").replace("<b>", "").replace("</b>", "").replace("*", "")
                    
                    enviar_telegram(titulo, resumen, link)
                    vistos.add(link)
                    nuevos += 1
                    time.sleep(1)
        except Exception as e:
            print(f"Error procesando {rss_url}: {e}")

    guardar_historial(vistos)
    print(f"Proceso finalizado. Nuevas alertas enviadas: {nuevos}")

if __name__ == "__main__":
    main()
