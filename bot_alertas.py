import os
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

# Exclusiones de contexto e industrias no relevantes
PALABRAS_EXCLUIDAS = [
    "fotograf", "deport", "fútbol", "futbol", "poesía", "poesia", "teatro",
    "salud mental", "accidente", "policial", "violencia", "música", "musica",
    "literario", "escultura", "danza", "legislativo", "carnaval", "farándula",
    "espectáculo", "vecinal", "tránsito", "homicidio", "robo", "hurto",
    "curso legal", "en el curso de", "tomó su curso", "curso de las acciones",
    "bolsa de comercio", "dólar", "dolar", "cripto", "bitcoin", "horóscopo"
]

# FACTOR 1: Debe ser explícitamente una oportunidad o actividad formativa/laboral
PALABRAS_OPORTUNIDAD = [
    "beca", "becas", "pasantia", "pasantía", "pps", "practica supervisada",
    "práctica supervisada", "convocatoria", "inscripcion", "inscripción",
    "taller", "curso", "capacitacion", "capacitación", "hackathon", "concurso",
    "busqueda laboral", "búsqueda laboral", "jovenes profesionales",
    "jóvenes profesionales", "bootcamp", "seminario", "webinar",
    "financiamiento", "subsidio", "movilidad", "proyecto de investigacion",
    "proyecto de investigación", "incubadora", "aceleradora"
]

# FACTOR 2: Nicho técnico (IA, Electrónica, Sistemas Embebidos, Hardware, Software)
PALABRAS_AREA = [
    # Inteligencia Artificial y Datos
    "ia", "inteligencia artificial", "machine learning", "deep learning",
    "vision artificial", "visión artificial", "redes neuronales", "llm",
    "ciencia de datos", "analisis de datos", "análisis de datos",
    # Electrónica y Sistemas Embebidos
    "electronica", "electrónica", "sistemas embebidos", "embebido", "embebidos",
    "microcontrolador", "microcontroladores", "esp32", "stm32", "arduino",
    "fpga", "pcb", "firmware", "vhdl", "verilog", "hardware", "iot",
    "internet de las cosas", "automatizacion", "automatización", "robotica",
    "robótica", "telecomunicaciones", "sensores", "instrumentacion",
    "instrumentación", "energia renovable", "energías renovables",
    # Ingeniería y Desarrollo
    "ingenieria", "ingeniería", "sistemas", "software", "programacion",
    "programación", "ciberseguridad"
]

# FACTOR 3: Candado Geográfico Estricto (Solo Tucumán e instituciones locales)
PALABRAS_TUCUMAN = [
    "tucuman", "tucumán", "san miguel de tucuman", "san miguel de tucumán",
    "utn frt", "utn-frt", "facultad regional tucuman", "facultad regional tucumán",
    "unt", "universidad nacional de tucuman", "universidad nacional de tucumán",
    "facet", "unsta", "uspt", "copit", "sidetec",
    "conicet tucuman", "conicet tucumán", "cerela", "proimi", "insibio",
    "inbiofal", "inta famailla", "inta famaillá", "eeaoc",
    "yerba buena", "tafi viejo", "tafí viejo", "banda del rio sali",
    "banda del río salí", "concepcion tucuman", "monteros", "aguilares", "lules"
]

# Carril Rápido (Auto-Aprobado directo si cumple los 3 factores y viene de fuentes locales clave)
PALABRAS_CONFIANZA_TOTAL = [
    "utn frt", "utn-frt", "facet", "sidetec", "copit", "conicet tucuman",
    "conicet tucumán", "beca ypf", "becas ypf"
]

STOP_WORDS = {
    "de", "la", "que", "el", "en", "y", "a", "los", "del", "se", "las", "por", "un", "para", "con", "no", "una", "su", "al", "lo", "como", "mas", "pero", "sus", "le", "ya", "o", "este", "si", "porque", "esta", "entre", "cuando", "muy", "sin", "sobre", "tambien", "me", "hasta", "hay", "donde", "quien", "desde", "nos", "durante", "uno", "ni", "contra", "ese", "eso", "ante", "ellos", "e", "esto", "mi", "antes", "algunos", "unos", "yo", "otro", "otras", "otra", "otros"
}

def normalizar_texto(texto):
    """Convierte a minúsculas y quita tildes para comparaciones limpias."""
    texto = texto.lower()
    return unicodedata.normalize('NFD', texto).encode('ascii', 'ignore').decode('utf-8')

def contiene_termino_exacto(texto_normalizado, lista_terminos):
    """Busca coincidencias de palabra completa para evitar falsos positivos (ej: 'ia' en 'provincia')."""
    for termino in lista_terminos:
        termino_norm = normalizar_texto(termino)
        patron = r'\b' + re.escape(termino_norm) + r'\b'
        if re.search(patron, texto_normalizado):
            return True
    return False

def limpiar_coletillas_titulo(titulo):
    """Elimina el nombre del medio al final del título (ej: 'Noticia - La Gaceta' -> 'Noticia')."""
    titulo_limpio = re.sub(r'\s*[\-\|]\s*.*$', '', titulo)
    return titulo_limpio.strip()

def limpiar_url(url):
    if "google.com/url" in url:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "url" in params:
            url = params["url"][0]
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))

def extraer_palabras_clave(texto):
    texto_norm = normalizar_texto(texto)
    palabras = re.findall(r'\b[a-z0-9]{3,}\b', texto_norm)
    return set(p for p in palabras if p not in STOP_WORDS)

def es_duplicado_por_similitud(titulo_nuevo, lista_titulos_existentes):
    t_nuevo_limpio = limpiar_coletillas_titulo(titulo_nuevo)
    kw_nuevo = extraer_palabras_clave(t_nuevo_limpio)
    
    if not kw_nuevo:
        return False

    for t_existente in lista_titulos_existentes:
        t_existente_limpio = limpiar_coletillas_titulo(t_existente)
        kw_existente = extraer_palabras_clave(t_existente_limpio)
        if not kw_existente:
            continue
        
        interseccion = kw_nuevo.intersection(kw_existente)
        similitud = len(interseccion) / max(len(kw_nuevo), len(kw_existente))
        
        if similitud >= 0.55:
            return True
    return False

def categorizar_noticia(titulo, resumen):
    texto = normalizar_texto(f"{titulo} {resumen}")
    if any(k in texto for k in ["beca", "becas", "posgrado", "financiamiento", "movilidad"]):
        return "🎓 BECAS Y POSGRADOS"
    elif any(k in texto for k in ["pasantia", "pps", "practica supervisada", "jovenes profesionales"]):
        return "💼 PASANTÍAS Y PPS"
    elif any(k in texto for k in ["taller", "curso", "capacitacion", "certificacion", "bootcamp"]):
        return "🛠️ TALLERES Y CURSOS"
    elif any(k in texto for k in ["concurso", "hackathon", "competencia", "ideaton", "desafio"]):
        return "🏆 CONCURSOS Y HACKATHONS"
    elif any(k in texto for k in ["congreso", "jornada", "jornadas", "simposio", "seminario"]):
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
    texto_norm = normalizar_texto(f"{titulo} {resumen}")
    
    # 1. Descarte por ruido o temas ajenos
    if any(normalizar_texto(p) in texto_norm for p in PALABRAS_EXCLUIDAS):
        return False
        
    # 2. TRIPLE FACTOR OBLIGATORIO: Oportunidad + Área Técnica + Tucumán
    tiene_oportunidad = contiene_termino_exacto(texto_norm, PALABRAS_OPORTUNIDAD)
    tiene_area = contiene_termino_exacto(texto_norm, PALABRAS_AREA)
    es_tucuman = contiene_termino_exacto(texto_norm, PALABRAS_TUCUMAN)
    
    return tiene_oportunidad and tiene_area and es_tucuman

def es_confianza_total(titulo, resumen):
    texto_norm = normalizar_texto(f"{titulo} {resumen}")
    return contiene_termino_exacto(texto_norm, PALABRAS_CONFIANZA_TOTAL)

def armar_borrador_whatsapp(titulo, resumen, link, categoria):
    titulo_limpio = limpiar_coletillas_titulo(titulo)
    return (
        f"{categoria}\n\n"
        f"📌 *{titulo_limpio}*\n\n"
        f"📝 {resumen}\n\n"
        f"🔗 {link}\n\n"
        f"--\n"
        f"_Gestión Estudiantil / Novedades UTN FRT_"
    )

def obtener_historial_desde_sheets():
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

def guardar_en_sheets_inicial(fecha, titulo, borrador, link, categoria, fecha_limite, estado="En Espera"):
    if not SHEETS_URL:
        return None
    payload = {
        "action": "noticia_nueva",
        "fecha": fecha,
        "titulo": titulo,
        "borrador": borrador,
        "link": link,
        "categoria": categoria,
        "fecha_limite": fecha_limite,
        "estado": estado
    }
    try:
        r = requests.post(SHEETS_URL, json=payload, timeout=10)
        res = r.json()
        return res.get("row_id")
    except Exception as e:
        print(f"Error registrando en Sheets: {e}")
        return None

def enviar_telegram_simple(mensaje):
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
        print(f"Error enviando mensaje simple a Telegram: {e}")

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

    vistos_links, vistos_titulos = obtener_historial_desde_sheets()
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")

    for rss_url in rss_urls:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                link = limpiar_url(entry.link)
                titulo = entry.title.replace("*", "")
                resumen = entry.get("summary", "").replace("<b>", "").replace("</b>", "").replace("*", "")

                if link in vistos_links or es_duplicado_por_similitud(titulo, vistos_titulos):
                    continue

                vistos_links.add(link)
                vistos_titulos.append(limpiar_coletillas_titulo(titulo))

                if es_noticia_valida(titulo, resumen):
                    categoria = categorizar_noticia(titulo, resumen)
                    fecha_limite = extraer_fecha_limite(f"{titulo} {resumen}")
                    titulo_limpio = limpiar_coletillas_titulo(titulo)
                    borrador = armar_borrador_whatsapp(titulo_limpio, resumen, link, categoria)

                    if es_confianza_total(titulo, resumen):
                        row_id = guardar_en_sheets_inicial(fecha_hoy, titulo_limpio, borrador, link, categoria, fecha_limite, estado="Aprobado")
                        if row_id:
                            mensaje_auto = f"⚡ *AUTO-APROBADA (CARRIL RÁPIDO)*\n\n{borrador}"
                            enviar_telegram_simple(mensaje_auto)
                    else:
                        row_id = guardar_en_sheets_inicial(fecha_hoy, titulo_limpio, borrador, link, categoria, fecha_limite, estado="En Espera")
                        if row_id:
                            enviar_telegram_con_botones(borrador, row_id)
                    time.sleep(1)
        except Exception as e:
            print(f"Error procesando {rss_url}: {e}")

if __name__ == "__main__":
    main()
