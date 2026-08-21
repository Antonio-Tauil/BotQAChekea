"""
config.py — Todo lo configurable del bot, en un solo lugar.

Si necesitas cambiar la hora del reporte, los emojis o las palabras clave,
este es el UNICO archivo que tienes que tocar.
"""

import os

# ---------------------------------------------------------------------------
# 1. CREDENCIALES Y CANALES (vienen de las variables de Railway)
# ---------------------------------------------------------------------------

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN", "")

# Canal donde QA reporta (de donde lee el bot)
CANAL_QA = os.environ.get("CANAL_QA", "")

# Canal donde se publica el reporte (hoy es el mismo #qa)
CANAL_REPORTE = os.environ.get("CANAL_REPORTE", "") or CANAL_QA

# Zona horaria. Railway corre en UTC; sin esto el reporte saldria 4 horas antes.
ZONA_HORARIA = os.environ.get("TZ", "America/Caracas")


# ---------------------------------------------------------------------------
# 2. CUANDO SE PUBLICA EL REPORTE AUTOMATICO
# ---------------------------------------------------------------------------

# Formato 24 horas, "HH:MM". Por defecto 6:00 PM hora Venezuela.
HORA_REPORTE = os.environ.get("HORA_REPORTE", "18:00")

# Dias en que corre el reporte automatico.
# "lun-vie" = solo dias laborales. Pon "*" si lo quieres todos los dias.
DIAS_REPORTE = os.environ.get("DIAS_REPORTE", "mon-fri")

# Desde que hora del dia se leen los mensajes (hora local).
# 0 = desde la medianoche.
HORA_INICIO_LECTURA = int(os.environ.get("HORA_INICIO_LECTURA", "0"))

# Cuantos dias hacia atras revisa el reporte AUTOMATICO de la tarde.
#   1  = solo hoy (lo normal para un reporte diario)
#   7  = la ultima semana
#   0  = todo el historial del canal
# Ojo: si lo pones en 0, el reporte automatico va a repetir los mismos bugs
# todos los dias. Para un barrido completo es mejor pedirlo a mano con
# "/qa-reporte todo", que no cambia el comportamiento diario.
DIAS_A_REVISAR = int(os.environ.get("DIAS_A_REVISAR", "1"))

# Tope de paginas al leer el historial (200 mensajes por pagina).
# Protege de que un "/qa-reporte todo" en un canal enorme se quede colgado.
MAX_PAGINAS_HISTORIAL = int(os.environ.get("MAX_PAGINAS_HISTORIAL", "25"))


# ---------------------------------------------------------------------------
# 3. LOS EMOJIS CON QUE QA CLASIFICA
# ---------------------------------------------------------------------------
# La clave es el NOMBRE del emoji en Slack (sin los dos puntos), no el dibujo.
# Para ver el nombre de un emoji: en Slack, pasa el mouse por encima de una
# reaccion y te lo muestra.

EMOJIS_SEVERIDAD = {
    # --- Critico (rojo) ---
    "red_circle": "critico",
    "large_red_circle": "critico",
    "rotating_light": "critico",       # 🚨
    "bangbang": "critico",             # ‼️
    "sos": "critico",
    # --- Alto (naranja) ---
    "large_orange_circle": "alto",
    "orange_circle": "alto",
    "warning": "alto",                 # ⚠️
    # --- Medio (amarillo) ---
    "large_yellow_circle": "medio",
    "yellow_circle": "medio",
    # --- Bajo (verde) ---
    "large_green_circle": "bajo",
    "green_circle": "bajo",
}

# Slack cambia el nombre interno de algunos emojis segun la version. Por eso
# arriba aceptamos varios alias del mismo color: si el equipo usa el circulo
# rojo, da igual si Slack lo llama "red_circle" o "large_red_circle".

# Si alguien reacciona con uno de estos sobre un bug ya reportado, el bug
# deja de aparecer en el reporte (aunque tambien tenga 🔴🟠🟡🟢). Asi un bug
# critico de hace 3 dias no sigue saliendo para siempre solo porque nadie
# "lo borro" -- basta con marcarlo como resuelto.
EMOJIS_RESUELTO = {
    "white_check_mark",     # ✅
    "heavy_check_mark",     # ✔️
    "ballot_box_with_check",  # ☑️
}

# Como se ve cada nivel en el reporte. El orden de este diccionario es el
# orden en que aparecen las secciones (lo mas grave primero).
NIVELES = {
    "critico": {"emoji": "🔴", "titulo": "CRÍTICOS", "color": "#C0392B"},
    "alto":    {"emoji": "🟠", "titulo": "ALTOS",    "color": "#DD6B20"},
    "medio":   {"emoji": "🟡", "titulo": "MEDIOS",   "color": "#D69E2E"},
    "bajo":    {"emoji": "🟢", "titulo": "BAJOS",    "color": "#2F855A"},
}

COLOR_SIN_MARCAR = "#3D7EC2"
COLOR_ERROR = "#C0392B"


# ---------------------------------------------------------------------------
# 4. PALABRAS CLAVE — la red de seguridad
# ---------------------------------------------------------------------------
# Mensajes que NADIE marco con emoji, pero que contienen alguna de estas
# palabras, salen al final del reporte en "posibles bugs sin marcar".
#
# COMO AJUSTAR ESTA LISTA:
#   - Si el reporte trae mucho ruido -> quita las palabras muy generales.
#   - Si se escapan bugs -> agrega las palabras que el equipo usa de verdad.
# Se comparan sin acentos y sin mayusculas, asi que escribelas en minuscula.

PALABRAS_CLAVE = [
    # fallas explicitas
    "no funciona", "no sirve", "no anda", "no jala",
    "falla", "fallo", "fallando", "error", "bug",
    "roto", "rota", "se rompio", "se dano",
    # crashes / cierres
    "se cierra", "se cerro", "se me cerro", "crash", "crashea",
    "se cae", "se cayo", "se traba", "se trabo", "se congela", "se queda pegado",
    # cosas que no aparecen o no llegan
    "no carga", "no abre", "no aparece", "no muestra", "no me llega",
    "no llega", "no llegan", "no deja", "no permite", "no responde",
    "no guarda", "no guardo", "no actualiza", "no refleja",
    "desaparecio", "se borro", "se perdio",
    # rendimiento
    "lento", "lentisimo", "tarda", "demora", "se demora", "pesado",
    # senales de alerta que usa la gente
    "alerta", "urgente", "critico", "grave", "ojo con", "cuidado con",
    "problema", "inconsistencia", "duplicado", "duplicada",
    # incorrecto
    "esta mal", "sale mal", "quedo mal", "incorrecto", "equivocado",
    "no coincide", "no cuadra", "raro", "extrano",
]

# Palabras que ANULAN una coincidencia. Si el mensaje trae alguna de estas,
# se asume que es conversacion y no un reporte.
# Ejemplo: "ya no falla" o "el error quedo resuelto" no son bugs nuevos.
PALABRAS_ANULAN = [
    "ya funciona", "ya sirve", "ya quedo", "quedo resuelto", "resuelto",
    "solucionado", "arreglado", "ya no falla", "corregido", "listo el",
    "buenos dias", "buenas tardes", "gracias",
]

# Mensajes mas cortos que esto (en caracteres) se ignoran en la busqueda por
# palabras clave. Evita que "ok", "listo", "si", "dale" llenen el reporte.
# Ojo: no lo subas mucho. Reportes cortos pero reales como "el login esta raro"
# (18 caracteres) son justo los que queremos que salgan a la luz.
LARGO_MINIMO_MENSAJE = 12

# Antes de publicar el reporte automatico, el bot revisa si ya publico uno
# hace poco (por si Railway lo reinicio justo a esa hora). Solo mira hacia
# atras esta cantidad de minutos: asi una prueba manual del mediodia NO
# cancela el reporte automatico de la tarde.
VENTANA_ANTIDUPLICADO_MINUTOS = 90

# Cuantos mensajes "sin marcar" mostrar como maximo (los mas recientes).
MAX_SIN_MARCAR = 8

# Cuantos bugs mostrar como maximo por nivel de severidad. Si un dia hay mas,
# se muestran los mas recientes y el reporte dice cuantos quedaron fuera
# (nunca los esconde en silencio).
MAX_POR_NIVEL = 15

# Largo maximo del texto de cada mensaje dentro del reporte.
# Si es mas largo, se corta y queda el enlace para ver el original completo.
MAX_LARGO_TEXTO = 400


# ---------------------------------------------------------------------------
# 5. QUIEN SE IGNORA
# ---------------------------------------------------------------------------
# IDs de usuarios cuyos mensajes nunca se toman en cuenta (otros bots,
# integraciones). Se escriben separados por coma en la variable de Railway.
# Los mensajes de aplicaciones ya se ignoran solos, esto es para personas.

USUARIOS_IGNORADOS = [
    u.strip() for u in os.environ.get("USUARIOS_IGNORADOS", "").split(",") if u.strip()
]


# ---------------------------------------------------------------------------
# 6. TEXTOS FIJOS
# ---------------------------------------------------------------------------

# Marca invisible que el bot pone en su propio reporte, para reconocerlo
# despues y no publicar dos veces el mismo dia. No la cambies.
MARCA_REPORTE = "qa-reporte-diario-v1"

LEYENDA_EMOJIS = (
    "🔴 crítico  ·  🟠 alto  ·  🟡 medio  ·  🟢 bajo — "
    "reacciona sobre el mensaje para clasificarlo."
)


def revisar_configuracion():
    """Avisa apenas arranca si falta alguna variable obligatoria."""
    faltantes = []
    if not SLACK_BOT_TOKEN:
        faltantes.append("SLACK_BOT_TOKEN")
    if not SLACK_APP_TOKEN:
        faltantes.append("SLACK_APP_TOKEN")
    if not CANAL_QA:
        faltantes.append("CANAL_QA")
    if faltantes:
        raise SystemExit(
            "FALTAN VARIABLES DE ENTORNO EN RAILWAY: "
            + ", ".join(faltantes)
            + "\nRevisa la pestana Variables del servicio."
        )


# ---------------------------------------------------------------------------
# 9. DIAGNOSTICO
# ---------------------------------------------------------------------------
# Cuando /qa-reporte no encuentra lo que esperabas, esto te dice exactamente
# que leyo el bot: cuantos mensajes, en que rango de horas, y que reacciones
# vio realmente en el canal. La respuesta la ve SOLO quien corrio el comando.
DIAGNOSTICO = os.environ.get("DIAGNOSTICO", "1") == "1"
