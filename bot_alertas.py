import os
import json
import time
import re
import unicodedata
from datetime import datetime
from urllib.parse import parse_qs, urlparse
import feedparser
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SHEETS_URL = os.environ.get("GOOGLE_SHEETS_WEBAPP_URL")

HISTORIAL_FILE = "enlaces_vistos.json"
RSS_FILE = "rss_urls.txt"

PALABRAS_EXCLUIDAS = [
    "fotograf", "deport", "fútbol", "futbol", "poesía", "poesia", "teatro",
    "salud mental", "accidente", "policial", "violencia", "música", "musica",
    "literario", "escultura", "danza", "legislativo", "carnaval", "farándula",
    "espectáculo", "vecinal", "tránsito", "homicidio", "robo", "hurto"
]

PALABRAS_INCLUSION = [
    "ingenieria", "ingeniería", "electronica", "electrónica", "sistemas",
    "software", "programacion", "programación", "hardware", "embebido",
    "embebidos", "iot", "telecomunicaciones", "ciberseguridad", "inteligencia artificial",
    "datos", "utn", "facet", "copit", "sidetec", "ieee", "balseiro",
    "conae", "invap", "pasantia", "pasantía", "pps", "practica supervisada",
    "práctica supervisada", "beca", "becas", "hackathon", "robotica", "robótica"
]

def limpiar_url(url):
    """Extrae la URL destino real eliminando el redireccionador de Google Alerts."""
    if "google.com/url" in url:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "url" in params:
            return params["url"][0]
    return url

def categorizar_noticia(titulo, resumen):
    """Asigna automáticamente una categoría visual basada en palabras clave."""
    texto = f"{titulo} {resumen}".lower()
    if any(k in texto for k in ["beca", "becas", "posgrado", "financiamiento", "movilidad"]):
        return "🎓 BECAS Y POSGRADOS"
    elif any(k in texto for k in ["pasantia", "pasantía", "pps", "practica supervisada", "práctica supervisada", "jovenes profesionales"]):
        return "💼 PASANTÍAS Y PPS"
    elif any(k in texto for k in ["taller", "curso", "capacitacion", "capacitación", "certificacion", "certificación"]):
        return "🛠️ TALLERES Y CURSOS"
    elif any(k in texto for k in ["concurso", "hackathon", "competencia", "ideaton", "ideatón", "desafío"]):
        return "🏆 CONCURSOS Y HACKATHONS"
    elif any(k in texto for k in ["congreso", "jornada", "jornadas", "simposio", "call for papers", "seminario"]):
        return "🏛️ CONGRESOS Y EVENTOS"
    return "📌 NOVEDADES GENERALES"

def normalizar_texto(texto):
    texto = texto.lower()
    texto = unicodedata.normalize('NFD', texto).encode('ascii', 'ignore').decode('utf-8')
    return re.sub(r'[^a-z0-9]', '', texto)

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
    texto = f"{titulo} {resumen}".lower()
    if any(p in texto for p in PALABRAS_EXCLUIDAS):
        return False
    return any(p in texto for p in PALABRAS_INCLUSION)

def armar_borrador_whatsapp(titulo, resumen, link, categoria):
    return (
        f"{categoria}\n\n"
        f"📌 *{titulo}*\n\n"
        f"📝 {resumen}\n\n"
        f"🔗 {link}\n\n"
        f"--\n"
        f"_Gestión Estudiantil / Novedades UTN_"
    )

def guardar_en_sheets_inicial(fecha, titulo, borrador, link, categoria):
    if not SHEETS_URL:
        return None
    payload = {
        "action": "noticia_nueva",
        "fecha": fecha,
        "titulo": titulo,
        "borrador": borrador,
        "link": link,
        "categoria": categoria
    }
    try:
        r = requests.post(SHEETS_URL, json=payload, timeout=10)
        res = r.json()
        return res.get("row_id")
    except Exception as e:
        print(f"Error registrando en Sheets: {e}")
        return None

def enviar_telegram_con_botones(borrador, row_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "💾 Guardar", "callback_data": f"save_{row_id}"},
                {"text": "🟩 Aprobar", "callback_data": f"appr_{row_id}"},
                {"text": "❌ Descartar", "callback_data": f"disc_{row_id}"}
            ]
        ]
    }
    payload = {
        "chat_id": CHAT_ID,
        "text": borrador,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
        "reply_markup": reply_markup
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error enviando a Telegram: {e}")

def main():
    if not os.path.exists(RSS_FILE):
        return

    with open(RSS_FILE, "r", encoding="utf-8") as f:
        rss_urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    vistos = cargar_historial()
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")

    for rss_url in rss_urls:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                link = limpiar_url(entry.link)
                titulo = entry.title.replace("*", "")
                resumen = entry.get("summary", "").replace("<b>", "").replace("</b>", "").replace("*", "")
                titulo_norm = normalizar_texto(titulo)

                if link in vistos or (titulo_norm and titulo_norm in vistos):
                    continue

                vistos.add(link)
                if titulo_norm:
                    vistos.add(titulo_norm)

                if es_noticia_valida(titulo, resumen):
                    categoria = categorizar_noticia(titulo, resumen)
                    borrador = armar_borrador_whatsapp(titulo, resumen, link, categoria)
                    row_id = guardar_en_sheets_inicial(fecha_hoy, titulo, borrador, link, categoria)
                    if row_id:
                        enviar_telegram_con_botones(borrador, row_id)
                    time.sleep(1)
        except Exception as e:
            print(f"Error procesando {rss_url}: {e}")

    guardar_historial(vistos)

if __name__ == "__main__":
    main()
