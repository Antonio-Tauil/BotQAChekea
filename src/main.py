"""
main.py — Arranque del bot.

Conecta las tres piezas (lector -> clasificador -> reporte) y las dispara
de dos formas:
  - a mano, con el comando /qa-reporte
  - solo, todos los dias a la hora configurada
"""

import logging
import sys

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


def generar_y_publicar(client, revisar_duplicado=False):
    """El trabajo completo: leer, clasificar, armar y publicar."""
    try:
        mensajes, total_crudos = lector.leer_dia(client)
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
        )
    except Exception as e:
        log.exception("Fallo generando el reporte")
        texto, blocks, attachments = reporte.construir_error(e)
        resultado = None

    if revisar_duplicado:
        desde, _ = lector.rango_del_dia()
        if reporte.ya_se_publico_hoy(client, config.CANAL_REPORTE, desde):
            log.info("El reporte de hoy ya estaba publicado. No se repite.")
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
def comando_reporte(ack, respond, client):
    # Confirmamos a Slack de inmediato (tenemos 3 segundos) y despues
    # hacemos el trabajo pesado. Es la leccion aprendida con /cobro.
    ack()
    try:
        generar_y_publicar(client, revisar_duplicado=False)
    except Exception as e:
        log.exception("Fallo el comando /qa-reporte")
        respond(f"No pude generar el reporte: {e}")


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
