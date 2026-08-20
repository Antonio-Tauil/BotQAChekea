"""
lector.py — Baja del canal de QA los mensajes del dia.

Se encarga de:
  - pedirle a Slack los mensajes desde la hora de inicio hasta ahora
  - traer tambien las respuestas dentro de hilos (Slack no las manda solas)
  - descartar mensajes de aplicaciones y avisos del sistema
  - resolver el nombre real de cada persona
  - conseguir el enlace directo a cada mensaje
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from slack_sdk.errors import SlackApiError

import config


# Subtipos de mensaje que son avisos del sistema, no conversacion real.
SUBTIPOS_IGNORADOS = {
    "channel_join", "channel_leave", "channel_topic", "channel_purpose",
    "channel_name", "channel_archive", "channel_unarchive",
    "bot_message", "message_changed", "message_deleted",
    "thread_broadcast_join", "pinned_item", "unpinned_item",
}


def _zona():
    return ZoneInfo(config.ZONA_HORARIA)


def rango_del_dia(momento=None):
    """Devuelve (inicio, fin) del dia de hoy como timestamps de Unix."""
    ahora = momento or datetime.now(_zona())
    inicio = ahora.replace(
        hour=config.HORA_INICIO_LECTURA, minute=0, second=0, microsecond=0
    )
    if ahora < inicio:  # por si se corre de madrugada
        inicio = inicio - timedelta(days=1)
    return inicio.timestamp(), ahora.timestamp()


def _es_mensaje_util(msg):
    """True si el mensaje es de una persona y tiene texto."""
    if msg.get("bot_id") or msg.get("app_id"):
        return False
    if msg.get("subtype") in SUBTIPOS_IGNORADOS:
        return False
    if not (msg.get("text") or "").strip():
        return False
    if msg.get("user") in config.USUARIOS_IGNORADOS:
        return False
    return True


def _paginar_historial(client, canal, desde, hasta):
    """Trae todos los mensajes del canal en el rango, pagina por pagina."""
    mensajes = []
    cursor = None
    for _ in range(20):  # tope de seguridad: 20 paginas (4000 mensajes)
        resp = client.conversations_history(
            channel=canal,
            oldest=str(desde),
            latest=str(hasta),
            inclusive=True,
            limit=200,
            cursor=cursor,
        )
        mensajes.extend(resp.get("messages", []) or [])
        cursor = (resp.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break
    return mensajes


def _traer_respuestas_de_hilos(client, canal, mensajes, desde, hasta):
    """Slack no entrega las respuestas de hilos junto con el canal.
    Aqui las pedimos aparte, solo para los mensajes que tienen hilo."""
    extras = []
    padres = [m for m in mensajes if m.get("reply_count")]
    for padre in padres[:40]:  # tope de seguridad
        try:
            resp = client.conversations_replies(
                channel=canal, ts=padre["ts"], limit=200
            )
        except SlackApiError:
            continue
        for r in resp.get("messages", []) or []:
            if r.get("ts") == padre.get("ts"):
                continue  # el primero es el padre, ya lo tenemos
            try:
                ts = float(r.get("ts", 0))
            except (TypeError, ValueError):
                continue
            if desde <= ts <= hasta:
                r["_en_hilo"] = True
                extras.append(r)
    return extras


class _CacheNombres:
    """Evita preguntarle a Slack el mismo usuario 20 veces."""

    def __init__(self, client):
        self.client = client
        self.cache = {}

    def nombre(self, user_id):
        if not user_id:
            return "Alguien"
        if user_id in self.cache:
            return self.cache[user_id]
        nombre = user_id
        try:
            info = self.client.users_info(user=user_id)
            perfil = (info.get("user") or {}).get("profile") or {}
            nombre = (
                perfil.get("display_name")
                or perfil.get("real_name")
                or (info.get("user") or {}).get("name")
                or user_id
            )
        except SlackApiError:
            pass
        self.cache[user_id] = nombre
        return nombre


def _permalink(client, canal, ts):
    try:
        resp = client.chat_getPermalink(channel=canal, message_ts=ts)
        return resp.get("permalink")
    except SlackApiError:
        return None


def leer_dia(client, canal=None, momento=None):
    """Devuelve la lista de mensajes utiles del dia, ya normalizados.

    Cada mensaje es un diccionario simple:
      {ts, texto, autor, hora, reacciones, adjuntos, enlace, en_hilo}
    """
    canal = canal or config.CANAL_QA
    desde, hasta = rango_del_dia(momento)

    crudos = _paginar_historial(client, canal, desde, hasta)
    crudos += _traer_respuestas_de_hilos(client, canal, crudos, desde, hasta)

    utiles = [m for m in crudos if _es_mensaje_util(m)]
    utiles.sort(key=lambda m: float(m.get("ts", 0)))

    nombres = _CacheNombres(client)
    zona = _zona()
    resultado = []

    for m in utiles:
        ts = m.get("ts")
        reacciones = [r.get("name") for r in (m.get("reactions") or [])]
        momento_msg = datetime.fromtimestamp(float(ts), zona)
        resultado.append(
            {
                "ts": ts,
                "texto": (m.get("text") or "").strip(),
                "autor": nombres.nombre(m.get("user")),
                "hora": momento_msg.strftime("%I:%M %p").lstrip("0").lower(),
                "reacciones": reacciones,
                "adjuntos": len(m.get("files") or []),
                "en_hilo": bool(m.get("_en_hilo")),
                "enlace": None,  # se llena despues, solo para los que salen
                "canal": canal,
            }
        )

    return resultado, len(crudos)


def completar_enlaces(client, mensajes):
    """Pide el enlace permanente solo de los mensajes que van al reporte.
    Se hace aparte para no gastar llamadas en mensajes que no se publican."""
    for m in mensajes:
        if m.get("enlace") is None:
            m["enlace"] = _permalink(client, m["canal"], m["ts"])
    return mensajes
