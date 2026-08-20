"""
reporte.py — Arma y publica el mensaje del reporte en Slack.

El reporte se construye con "attachments" de Slack: cada nivel de severidad
es un bloque con su barra de color a la izquierda. Dentro de cada bloque van
los mensajes de ese nivel, con el texto original y el enlace al mensaje.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import config

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_larga(momento=None):
    m = momento or datetime.now(ZoneInfo(config.ZONA_HORARIA))
    return f"{DIAS[m.weekday()]} {m.day} de {MESES[m.month - 1]}"


def _escapar(texto):
    """Slack usa < > & para su propio formato; hay que escaparlos."""
    return (texto or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _recortar(texto):
    texto = (texto or "").strip()
    if len(texto) <= config.MAX_LARGO_TEXTO:
        return texto
    return texto[: config.MAX_LARGO_TEXTO].rstrip() + "…"


def _cita(texto):
    """Convierte el texto en cita de Slack (barra gris a la izquierda)."""
    limpio = _escapar(_recortar(texto))
    return "\n".join("> " + linea for linea in limpio.split("\n"))


def _linea_mensaje(msg):
    """Un mensaje del reporte: quien, cuando, el texto y el enlace."""
    meta = [f"*{_escapar(msg['autor'])}*", msg["hora"]]
    if msg.get("adjuntos"):
        meta.append(f"📎 {msg['adjuntos']}")
    if msg.get("en_hilo"):
        meta.append("🧵 en hilo")

    partes = [" · ".join(meta), _cita(msg["texto"])]
    if msg.get("enlace"):
        partes.append(f"<{msg['enlace']}|Ver mensaje original ↗>")
    return "\n".join(partes)


# Slack corta cualquier bloque de texto que pase de 3000 caracteres.
# Dejamos margen y partimos en varios bloques si hace falta.
LARGO_MAXIMO_BLOQUE = 2800


def _seccion(texto):
    return {"type": "section", "text": {"type": "mrkdwn", "text": texto}}


def _secciones(piezas):
    """Convierte una lista de textos en uno o varios bloques 'section',
    sin que ninguno pase del limite de Slack."""
    bloques = []
    actual = []
    largo = 0
    for pieza in piezas:
        extra = len(pieza) + 2
        if actual and largo + extra > LARGO_MAXIMO_BLOQUE:
            bloques.append(_seccion("\n\n".join(actual)))
            actual, largo = [], 0
        # una sola pieza gigante: se recorta para que quepa
        if extra > LARGO_MAXIMO_BLOQUE:
            pieza = pieza[: LARGO_MAXIMO_BLOQUE - 20].rstrip() + "…"
            extra = len(pieza) + 2
        actual.append(pieza)
        largo += extra
    if actual:
        bloques.append(_seccion("\n\n".join(actual)))
    return bloques


def _contexto(texto):
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": texto}]}


def construir(resultado, total_mensajes, nombre_canal="#qa", momento=None):
    """Devuelve (texto_plano, blocks, attachments) listos para publicar."""
    marcados = resultado["marcados"]
    sin_marcar = resultado["sin_marcar"]

    # --- Encabezado (va en blocks, fuera de los attachments) ---
    conteos = []
    for nivel, datos in config.NIVELES.items():
        n = len(marcados[nivel])
        if n:
            conteos.append(f"{datos['emoji']} {n} {datos['titulo'].lower()}")

    resumen = (
        f"{nombre_canal} · {total_mensajes} mensajes revisados · "
        f"*{resultado['total_marcados']} marcados como bug*"
    )
    if sin_marcar:
        resumen += f" · {len(sin_marcar)} posibles sin marcar"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🧪 Reporte Diario de QA · {fecha_larga(momento)}",
                "emoji": True,
            },
        },
        _contexto(resumen),
    ]
    if conteos:
        blocks.append(_contexto("  ·  ".join(conteos)))

    # --- Caso: dia sin nada ---
    if not resultado["total_marcados"] and not sin_marcar:
        attachments = [
            {
                "color": config.NIVELES["bajo"]["color"],
                "blocks": [
                    _seccion(
                        "*✅ Sin bugs nuevos hoy*\n"
                        "Nadie marcó mensajes con 🔴🟠🟡🟢 y la revisión por "
                        "palabras clave tampoco encontró nada sospechoso."
                    )
                ],
            }
        ]
        blocks.append(_contexto(f"{config.LEYENDA_EMOJIS}\n_{config.MARCA_REPORTE}_"))
        return f"Reporte Diario de QA · {fecha_larga(momento)} · sin bugs", blocks, attachments

    # --- Un attachment por nivel de severidad ---
    attachments = []
    for nivel, datos in config.NIVELES.items():
        items = marcados[nivel]
        if not items:
            continue
        mostrados = items[: config.MAX_POR_NIVEL]
        ocultos = len(items) - len(mostrados)
        piezas = [f"*{datos['emoji']} {datos['titulo']} ({len(items)})*"]
        piezas.extend(_linea_mensaje(m) for m in mostrados)
        if ocultos:
            piezas.append(
                f"_(se muestran los {len(mostrados)} más recientes; "
                f"quedaron {ocultos} más de este nivel en el canal)_"
            )
        attachments.append({"color": datos["color"], "blocks": _secciones(piezas)})

    # --- Posibles bugs sin marcar ---
    if sin_marcar:
        piezas = [
            f"*🔍 POSIBLES BUGS SIN MARCAR ({len(sin_marcar)})*",
            "_Suenan a falla pero nadie les puso emoji. "
            "Si son bugs, márcalos y mañana salen clasificados arriba._",
        ]
        piezas.extend(_linea_mensaje(m) for m in sin_marcar)
        if resultado.get("sin_marcar_ocultos"):
            piezas.append(
                f"_(hay {resultado['sin_marcar_ocultos']} más que no se muestran "
                f"para no alargar el reporte)_"
            )
        attachments.append(
            {"color": config.COLOR_SIN_MARCAR, "blocks": _secciones(piezas)}
        )

    blocks.append(_contexto(f"{config.LEYENDA_EMOJIS}\n_{config.MARCA_REPORTE}_"))

    texto_plano = (
        f"Reporte Diario de QA · {fecha_larga(momento)} · "
        f"{resultado['total_marcados']} bugs marcados"
    )
    return texto_plano, blocks, attachments


def construir_error(motivo):
    """Mensaje que se publica cuando el reporte no se pudo generar.
    Es preferible un error visible a un silencio."""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "⚠️ No pude generar el reporte de hoy",
                "emoji": True,
            },
        }
    ]
    attachments = [
        {
            "color": config.COLOR_ERROR,
            "blocks": [
                _seccion(
                    f"*Motivo:* {_escapar(str(motivo))}\n\n"
                    "Lo más común es que el bot ya no esté invitado al canal. "
                    "El chat no se perdió: apenas se resuelva, se puede "
                    "regenerar con `/qa-reporte`."
                )
            ],
        }
    ]
    return "No pude generar el reporte de QA de hoy", blocks, attachments


def ya_se_publico_hoy(client, canal, desde_ts):
    """Revisa si el bot ya publico su reporte hoy, para no repetirlo si
    Railway lo reinicia cerca de la hora."""
    try:
        resp = client.conversations_history(
            channel=canal, oldest=str(desde_ts), limit=100
        )
    except Exception:
        return False
    for msg in resp.get("messages", []) or []:
        if config.MARCA_REPORTE in (msg.get("text") or ""):
            return True
        for bloque in msg.get("blocks", []) or []:
            for el in bloque.get("elements", []) or []:
                if config.MARCA_REPORTE in str(el.get("text", "")):
                    return True
    return False


def publicar(client, canal, texto, blocks, attachments):
    return client.chat_postMessage(
        channel=canal,
        text=texto,
        blocks=blocks,
        attachments=attachments,
        unfurl_links=False,
        unfurl_media=False,
    )
