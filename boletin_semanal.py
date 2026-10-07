import os
from collections import defaultdict
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

    # Agrupar las noticias aprobadas según su categoría
    categorias = defaultdict(list)
    for item in aprobados:
        cat = item.get("categoria", "📌 NOVEDADES GENERALES")
        categorias[cat].append(item)

    lineas = ["🗞️ *BOLETÍN SEMANAL DE BECAS Y OPORTUNIDADES*\n"]

    for cat_nombre, items in categorias.items():
        lineas.append(f"*{cat_nombre}*")
        for item in items:
            lineas.append(f"• *{item['titulo']}*")
            lineas.append(f"  🔗 {item['link']}")
        lineas.append("")

    lineas.append("---\n_Compilado por la Gestión Estudiantil UTN_")
    mensaje_boletin = "\n".join(lineas)

    url_tg = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensaje_boletin,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    requests.post(url_tg, json=payload, timeout=10)

    requests.get(f"{SHEETS_URL}?action=marcar_publicados", timeout=10)

if __name__ == "__main__":
    generar_boletin()
