"""
main.py — Arranque del bot.

Conecta las tres piezas (lector -> clasificador -> reporte) y las dispara
de dos formas:
  - a mano, con el comando /qa-reporte
  - solo, todos los dias a la hora configurada
"""

import logging
import sys
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from zoneinfo import ZoneInfo

import config
import lector
import clasificador
import reporte

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("botqa")

config.revisar_configuracion()

app = App(token=config.SLACK_BOT_TOKEN)


def _nombre_canal(client, canal_id):
    try:
        info = client.conversations_info(channel=canal_id)
        return "#" + (info.get("channel") or {}).get("name", "qa")
    except Exception:
        return "#qa"


def resumen_diagnostico(client, dias=None):
    """Texto corto que explica que vio el bot. Sirve para entender por que
    un reporte salio vacio, sin tener que abrir los logs de Railway."""
    try:
        desde, hasta = lector.rango_del_dia(dias=dias)
        zona = ZoneInfo(config.ZONA_HORARIA)
        h1 = ("el inicio del canal" if desde == 0
              else datetime.fromtimestamp(desde, zona).strftime("%d/%m %I:%M %p"))
        h2 = datetime.fromtimestamp(hasta, zona).strftime("%d/%m %I:%M %p")
        mensajes, crudos = lector.leer_dia(client, dias=dias)

        vistas = {}
        for m in mensajes:
            for r in m.get("reacciones") or []:
                vistas[r] = vistas.get(r, 0) + 1

        if vistas:
            reconocidas = [
                f"`:{n}:` x{c}" + ("  ✅" if n in config.EMOJIS_SEVERIDAD else "  ❌ no cuenta")
                for n, c in sorted(vistas.items(), key=lambda x: -x[1])
            ]
            texto_reacciones = "\n".join("• " + r for r in reconocidas)
        else:
            texto_reacciones = (
                "• _ninguna_ — no hay ni una sola reacción en los mensajes de "
                "este rango.\n  Si marcaste mensajes más viejos, prueba con "
                "`/qa-reporte todo` para revisar el historial completo."
            )

        return (
            f"*Diagnóstico de la última corrida*\n"
            f"• Rango leído: *{h1}* → *{h2}*\n"
            f"• Mensajes en ese rango: *{crudos}* "
            f"(útiles, sin apps ni avisos: *{len(mensajes)}*)\n"
            f"• Reacciones encontradas:\n{texto_reacciones}"
        )
    except Exception as e:
        return f"No pude armar el diagnóstico: {e}"


def interpretar_rango(texto):
    """Lee lo que la persona escribio despues de /qa-reporte.

      /qa-reporte           -> lo de siempre (segun DIAS_A_REVISAR)
      /qa-reporte 7         -> los ultimos 7 dias
      /qa-reporte todo      -> todo el historial del canal
    """
    limpio = (texto or "").strip().lower()
    if not limpio:
        return None
    if limpio in ("todo", "todos", "all", "historial", "completo"):
        return 0
    try:
        n = int(limpio)
        return n if 0 <= n <= 365 else None
    except ValueError:
        return None


def generar_y_publicar(client, revisar_duplicado=False, dias=None):
    """El trabajo completo: leer, clasificar, armar y publicar."""
    try:
        mensajes, total_crudos = lector.leer_dia(client, dias=dias)
        resultado = clasificador.clasificar(mensajes)

        # Solo pedimos el enlace de los mensajes que salen publicados.
        a_enlazar = list(resultado["sin_marcar"])
        for lista in resultado["marcados"].values():
            a_enlazar.extend(lista)
        lector.completar_enlaces(client, a_enlazar)

        texto, blocks, attachments = reporte.construir(
            resultado,
            total_mensajes=total_crudos,
            nombre_canal=_nombre_canal(client, config.CANAL_QA),
            rango=lector.describir_rango(dias),
        )
    except Exception as e:
        log.exception("Fallo generando el reporte")
        texto, blocks, attachments = reporte.construir_error(e)
        resultado = None

    if revisar_duplicado:
        # Solo miramos los ultimos minutos, no todo el dia: una prueba manual
        # con /qa-reporte no debe cancelar el reporte automatico de la tarde.
        desde = (
            datetime.now(ZoneInfo(config.ZONA_HORARIA))
            - timedelta(minutes=config.VENTANA_ANTIDUPLICADO_MINUTOS)
        ).timestamp()
        if reporte.ya_se_publico_hoy(client, config.CANAL_REPORTE, desde):
            log.info(
                "Ya se publico un reporte hace menos de %s minutos. No se repite.",
                config.VENTANA_ANTIDUPLICADO_MINUTOS,
            )
            return None

    respuesta = reporte.publicar(
        client, config.CANAL_REPORTE, texto, blocks, attachments
    )
    if resultado:
        log.info(
            "Reporte publicado: %s marcados, %s sin marcar",
            resultado["total_marcados"],
            len(resultado["sin_marcar"]),
        )
    return respuesta


# ---------------------------------------------------------------------------
# Comando manual: /qa-reporte
# ---------------------------------------------------------------------------

@app.command("/qa-reporte")
def comando_reporte(ack, respond, client, command):
    # Confirmamos a Slack de inmediato (tenemos 3 segundos) y despues
    # hacemos el trabajo pesado. Es la leccion aprendida con /cobro.
    ack()
    dias = interpretar_rango(command.get("text"))
    try:
        generar_y_publicar(client, revisar_duplicado=False, dias=dias)
        if config.DIAGNOSTICO:
            # Solo lo ve quien escribio el comando, no molesta al canal.
            respond(resumen_diagnostico(client, dias))
    except Exception as e:
        log.exception("Fallo el comando /qa-reporte")
        respond(f"No pude generar el reporte: {e}")


# ---------------------------------------------------------------------------
# Comando de ayuda: /qa-ayuda
# ---------------------------------------------------------------------------

@app.command("/qa-ayuda")
def comando_ayuda(ack, client, command):
    ack()
    try:
        texto, blocks, attachments = reporte.construir_ayuda()
        client.chat_postMessage(
            channel=command["channel_id"],
            text=texto,
            blocks=blocks,
            attachments=attachments,
        )
    except Exception:
        log.exception("Fallo el comando /qa-ayuda")


# ---------------------------------------------------------------------------
# Reporte automatico
# ---------------------------------------------------------------------------

def tarea_diaria():
    log.info("Corriendo el reporte automatico")
    generar_y_publicar(app.client, revisar_duplicado=True)


def arrancar_scheduler():
    try:
        hora, minuto = config.HORA_REPORTE.split(":")
        hora, minuto = int(hora), int(minuto)
    except ValueError:
        log.error("HORA_REPORTE mal escrita (%s). Uso 18:00.", config.HORA_REPORTE)
        hora, minuto = 18, 0

    zona = ZoneInfo(config.ZONA_HORARIA)
    scheduler = BackgroundScheduler(timezone=zona)
    scheduler.add_job(
        tarea_diaria,
        CronTrigger(
            day_of_week=config.DIAS_REPORTE,
            hour=hora,
            minute=minuto,
            timezone=zona,
        ),
        id="reporte_diario",
        misfire_grace_time=3600,   # si el bot reinicia, aun asi lo publica
        coalesce=True,             # si se acumularon disparos, ejecuta uno solo
        max_instances=1,
    )
    scheduler.start()
    log.info(
        "Reporte automatico programado: %02d:%02d (%s), dias %s",
        hora, minuto, config.ZONA_HORARIA, config.DIAS_REPORTE,
    )
    return scheduler


if __name__ == "__main__":
    arrancar_scheduler()
    log.info("Bot de QA arrancando (Socket Mode)...")
    try:
        SocketModeHandler(app, config.SLACK_APP_TOKEN).start()
    except KeyboardInterrupt:
        sys.exit(0)
