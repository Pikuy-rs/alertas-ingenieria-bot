import os
import json
import time
import re
import unicodedata
from datetime import datetime
from urllib.parse import parse_qs, urlparse, urlunparse
import feedparser
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SHEETS_URL = os.environ.get("GOOGLE_SHEETS_WEBAPP_URL")

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

STOP_WORDS = {
    "de", "la", "que", "el", "en", "y", "a", "los", "del", "se", "las", "por", "un", "para", "con", "no", "una", "su", "al", "lo", "como", "mas", "pero", "sus", "le", "ya", "o", "este", "si", "porque", "esta", "entre", "cuando", "muy", "sin", "sobre", "tambien", "me", "hasta", "hay", "donde", "quien", "desde", "nos", "durante", "uno", "ni", "contra", "ese", "eso", "ante", "ellos", "e", "esto", "mi", "antes", "algunos", "unos", "yo", "otro", "otras", "otra", "otros"
}

def limpiar_url(url):
    """Extrae la URL destino real y quita parámetros de rastreo."""
    if "google.com/url" in url:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "url" in params:
            url = params["url"][0]
    
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))

def extraer_palabras_clave(texto):
    """Retorna un conjunto de palabras clave significativas (sin conectores ni acentos)."""
    texto = texto.lower()
    texto = unicodedata.normalize('NFD', texto).encode('ascii', 'ignore').decode('utf-8')
    palabras = re.findall(r'\b[a-z0-9]{3,}\b', texto)
    return set(p for p in palabras if p not in STOP_WORDS)

def es_duplicado_por_similitud(titulo_nuevo, lista_titulos_existentes):
    """Evalúa si el título nuevo comparte más del 70% de palabras clave con alguno existente."""
    kw_nuevo = extraer_palabras_clave(titulo_nuevo)
    if not kw_nuevo:
        return False

    for t_existente in lista_titulos_existentes:
        kw_existente = extraer_palabras_clave(t_existente)
        if not kw_existente:
            continue
        
        interseccion = kw_nuevo.intersection(kw_existente)
        similitud = len(interseccion) / max(len(kw_nuevo), len(kw_existente))
        if similitud >= 0.7:
            return True
    return False

def categorizar_noticia(titulo, resumen):
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

def extraer_fecha_limite(texto):
    patrones = [
        r'(?:hasta|cierra|vence|límite|limite)\s+(?:el\s+)?(\d{1,2}[\/\.-]\d{1,2}(?:[\/\.-]\d{2,4})?)',
        r'(?:hasta|cierra|vence|límite|limite)\s+(?:el\s+)?(\d{1,2}\s+de\s+[a-zA-Z]+)',
    ]
    texto_lower = texto.lower()
    for pat in patrones:
        match = re.search(pat, texto_lower)
        if match:
            return match.group(1).title()
    return "Sin fecha detectada"

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

def obtener_historial_desde_sheets():
    """Descarga todo el historial almacenado en la planilla de Google."""
    if not SHEETS_URL:
        return set(), []
    try:
        res = requests.get(f"{SHEETS_URL}?action=obtener_historial", timeout=10)
        data = res.json()
        links = set(l.lower() for l in data.get("links", []))
        titulos = data.get("titulos", [])
        return links, titulos
    except Exception as e:
        print(f"Error cargando historial desde Sheets: {e}")
        return set(), []

def guardar_en_sheets_inicial(fecha, titulo, borrador, link, categoria, fecha_limite):
    if not SHEETS_URL:
        return None
    payload = {
        "action": "noticia_nueva",
        "fecha": fecha,
        "titulo": titulo,
        "borrador": borrador,
        "link": link,
        "categoria": categoria,
        "fecha_limite": fecha_limite
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

    # Cargar historial centralizado desde Google Sheets
    vistos_links, vistos_titulos = obtener_historial_desde_sheets()
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")

    for rss_url in rss_urls:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                link = limpiar_url(entry.link)
                titulo = entry.title.replace("*", "")
                resumen = entry.get("summary", "").replace("<b>", "").replace("</b>", "").replace("*", "")

                # Validación de duplicado por enlace o por similitud semántica de título
                if link in vistos_links or es_duplicado_por_similitud(titulo, vistos_titulos):
                    continue

                # Registrar inmediatamente en memoria local durante la corrida
                vistos_links.add(link)
                vistos_titulos.append(titulo)

                if es_noticia_valida(titulo, resumen):
                    categoria = categorizar_noticia(titulo, resumen)
                    fecha_limite = extraer_fecha_limite(f"{titulo} {resumen}")
                    borrador = armar_borrador_whatsapp(titulo, resumen, link, categoria)
                    
                    row_id = guardar_en_sheets_inicial(fecha_hoy, titulo, borrador, link, categoria, fecha_limite)
                    if row_id:
                        enviar_telegram_con_botones(borrador, row_id)
                    time.sleep(1)
        except Exception as e:
            print(f"Error procesando {rss_url}: {e}")

if __name__ == "__main__":
    main()
