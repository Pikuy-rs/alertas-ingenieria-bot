import os
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SHEETS_URL = os.environ.get("GOOGLE_SHEETS_WEBAPP_URL")

def generar_boletin():
    if not SHEETS_URL:
        return

    res = requests.get(SHEETS_URL, timeout=10)
    aprobados = res.json()

    if not aprobados:
        print("No hay noticias aprobadas esta semana.")
        return

    lineas = ["🗞️ *BOLETÍN SEMANAL DE BECAS Y OPORTUNIDADES*\n"]
    for idx, item in enumerate(aprobados, 1):
        lineas.append(f"{idx}. *{item['titulo']}*")
        lineas.append(f"🔗 {item['link']}\n")

    lineas.append("_Compilado de Novedades Académicas y Profesionales_")
    mensaje_boletin = "\n".join(lineas)

    url_tg = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensaje_boletin,
        "parse_mode": "Markdown"
    }
    requests.post(url_tg, json=payload, timeout=10)

    requests.get(f"{SHEETS_URL}?action=marcar_publicados", timeout=10)

if __name__ == "__main__":
    generar_boletin()
