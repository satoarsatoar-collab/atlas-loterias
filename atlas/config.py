"""Configuración central de ATLAS: loterías, calendario, rutas y umbrales estadísticos."""
from __future__ import annotations

import datetime as dt
import os
import unicodedata

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(RAIZ, "data")
INBOX = os.path.join(DATA, "inbox")
STORE = os.path.join(DATA, "store", "resultados.csv")
PROCESADOS = os.path.join(DATA, "procesados")
STATE = os.path.join(RAIZ, "state")
SITE = os.path.join(RAIZ, "site")

# Fecha desde la cual se cuenta la evidencia PROSPECTIVA (predicciones hechas antes de conocer el resultado).
# Todo lo anterior es "retrospectivo": sirve de contexto, nunca para declarar un patrón validado.
INICIO_PROSPECTIVO = "2026-10-17"

# Umbrales estadísticos
ALFA_FDR = 0.10        # tasa de falsos descubrimientos para e-BH ("patrón validado")
E_OBSERVACION = 20.0   # E individual >= 20 -> "en observación" (sin corregir por multiplicidad)

LOTERIAS = {
    # slug: (nombre, día de juego 0=lunes, alias aceptados en los CSV)
    "loteria-de-cundinamarca": ("Cundinamarca", 0, ["cundinamarca", "loteria de cundinamarca"]),
    "loteria-del-tolima": ("Tolima", 0, ["tolima", "loteria del tolima"]),
    "loteria-de-la-cruz-roja": ("Cruz Roja", 1, ["cruz roja", "cruzroja", "loteria de la cruz roja"]),
    "loteria-del-huila": ("Huila", 1, ["huila", "loteria del huila"]),
    "loteria-de-manizales": ("Manizales", 2, ["manizales", "loteria de manizales"]),
    "loteria-del-meta": ("Meta", 2, ["meta", "loteria del meta", "llanera"]),
    "loteria-del-valle": ("Valle", 2, ["valle", "loteria del valle"]),
    "loteria-de-bogota": ("Bogotá", 3, ["bogota", "loteria de bogota"]),
    "loteria-del-quindio": ("Quindío", 3, ["quindio", "loteria del quindio"]),
    "loteria-de-medellin": ("Medellín", 4, ["medellin", "loteria de medellin"]),
    "loteria-de-risaralda": ("Risaralda", 4, ["risaralda", "loteria de risaralda"]),
    "loteria-de-santander": ("Santander", 4, ["santander", "loteria de santander"]),
    "loteria-de-boyaca": ("Boyacá", 5, ["boyaca", "loteria de boyaca"]),
    "loteria-del-cauca": ("Cauca", 5, ["cauca", "loteria del cauca"]),
}
NOMBRE = {k: v[0] for k, v in LOTERIAS.items()}

# Series en juego por lotería (series 000 a S-1), estimadas en el estudio con los secos del 17-ago al 16-oct-2026.
# Si aparece una serie mayor, el sistema amplía S solo (redondeando a la decena).
SERIES_EMISION = {
    "loteria-de-bogota": 470, "loteria-de-boyaca": 470, "loteria-de-cundinamarca": 350, "loteria-de-la-cruz-roja": 330,
    "loteria-de-manizales": 400, "loteria-de-medellin": 500, "loteria-de-risaralda": 300, "loteria-de-santander": 340,
    "loteria-del-cauca": 310, "loteria-del-huila": 180, "loteria-del-meta": 150, "loteria-del-quindio": 200,
    "loteria-del-tolima": 280, "loteria-del-valle": 310,
}
INICIO_SERIES = "2026-08-17"   # antes de esta fecha la emisión de series de algunas loterías era otra


def normalizar_texto(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()
    return " ".join(s.replace("-", " ").replace("_", " ").split())


ALIAS = {}
for slug, (nombre, _, alias) in LOTERIAS.items():
    for a in alias + [nombre, slug]:
        ALIAS[normalizar_texto(a)] = slug


def slug_de(texto: str) -> str | None:
    return ALIAS.get(normalizar_texto(texto))


# ----------------------------------------------------------------- festivos de Colombia (Ley 51 de 1983)
def _pascua(y: int) -> dt.date:
    a = y % 19; b = y // 100; c = y % 100; d = b // 4; e = b % 4; f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30; i = c // 4; k = c % 4; l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451; mes = (h + l - 7 * m + 114) // 31; dia = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(y, mes, dia)


def _lunes_siguiente(d: dt.date) -> dt.date:
    return d + dt.timedelta(days=(7 - d.weekday()) % 7)


def festivos(y: int) -> set[dt.date]:
    fijos = [dt.date(y, 1, 1), dt.date(y, 5, 1), dt.date(y, 7, 20), dt.date(y, 8, 7), dt.date(y, 12, 8), dt.date(y, 12, 25)]
    trasladables = [dt.date(y, 1, 6), dt.date(y, 3, 19), dt.date(y, 6, 29), dt.date(y, 8, 15), dt.date(y, 10, 12),
                    dt.date(y, 11, 1), dt.date(y, 11, 11)]
    p = _pascua(y)
    moviles = [p - dt.timedelta(days=3), p - dt.timedelta(days=2)]
    moviles += [_lunes_siguiente(p + dt.timedelta(days=n)) for n in (39, 60, 68)]  # Ascensión, Corpus, Sagrado Corazón
    return set(fijos) | {_lunes_siguiente(d) for d in trasladables} | set(moviles)


def es_festivo(d: dt.date) -> bool:
    return d in festivos(d.year)


def proximos_sorteos(desde: dt.date, dias: int = 14) -> list[tuple[str, str]]:
    """Calendario esperado: si el día de juego es festivo, el sorteo pasa al siguiente día no festivo."""
    out = []
    for k in range(dias):
        d = desde + dt.timedelta(days=k)
        for slug, (_, wd, _) in LOTERIAS.items():
            if d.weekday() == wd:
                f = d
                while es_festivo(f):
                    f += dt.timedelta(days=1)
                out.append((slug, f.isoformat()))
    return sorted(set(out), key=lambda t: (t[1], t[0]))
