"""
clasificador.py — Decide que es bug y que tan grave es.

Dos señales, en este orden:
  1. REACCION EMOJI  -> señal principal. Si alguien puso 🔴🟠🟡🟢, no hay duda.
  2. PALABRAS CLAVE  -> red de seguridad. Mensajes que nadie marco pero suenan
                        a falla, van a la seccion "posibles bugs sin marcar".
"""

import unicodedata

import config


def _normalizar(texto):
    """Pasa a minusculas y quita acentos, para comparar sin sorpresas.
    'Se Cerró' y 'se cerro' tienen que dar lo mismo."""
    texto = (texto or "").lower()
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def severidad_por_reaccion(reacciones):
    """Si el mensaje tiene alguna reaccion de severidad, devuelve el nivel.
    Si tiene varias, gana la mas grave."""
    orden = list(config.NIVELES.keys())  # critico, alto, medio, bajo
    encontrados = [
        config.EMOJIS_SEVERIDAD[r]
        for r in (reacciones or [])
        if r in config.EMOJIS_SEVERIDAD
    ]
    if not encontrados:
        return None
    return min(encontrados, key=lambda n: orden.index(n))


def suena_a_falla(texto):
    """True si el texto contiene alguna palabra clave y ninguna que la anule.
    Devuelve tambien cual palabra hizo match, util para depurar."""
    limpio = _normalizar(texto)

    if len(limpio) < config.LARGO_MINIMO_MENSAJE:
        return False, None

    for anula in config.PALABRAS_ANULAN:
        if _normalizar(anula) in limpio:
            return False, None

    for palabra in config.PALABRAS_CLAVE:
        if _normalizar(palabra) in limpio:
            return True, palabra

    return False, None


def clasificar(mensajes):
    """Separa los mensajes del dia en marcados y sin marcar.

    Devuelve un diccionario:
      {
        "marcados":   {"critico": [...], "alto": [...], ...},
        "sin_marcar": [...],
        "total_marcados": int,
      }
    """
    marcados = {nivel: [] for nivel in config.NIVELES}
    sin_marcar = []

    for msg in mensajes:
        nivel = severidad_por_reaccion(msg.get("reacciones"))
        if nivel:
            marcados[nivel].append(msg)
            continue

        hay, palabra = suena_a_falla(msg.get("texto"))
        if hay:
            copia = dict(msg)
            copia["palabra_detectada"] = palabra
            sin_marcar.append(copia)

    # Los marcados van del mas reciente al mas viejo dentro de cada nivel.
    for nivel in marcados:
        marcados[nivel].sort(key=lambda m: float(m["ts"]), reverse=True)

    # De los sin marcar mostramos solo los mas recientes, para no llenar
    # el reporte de ruido.
    sin_marcar.sort(key=lambda m: float(m["ts"]), reverse=True)
    sobrantes = max(0, len(sin_marcar) - config.MAX_SIN_MARCAR)
    sin_marcar = sin_marcar[: config.MAX_SIN_MARCAR]

    return {
        "marcados": marcados,
        "sin_marcar": sin_marcar,
        "sin_marcar_ocultos": sobrantes,
        "total_marcados": sum(len(v) for v in marcados.values()),
    }
