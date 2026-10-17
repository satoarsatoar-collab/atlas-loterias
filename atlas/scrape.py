"""Descarga automática de sorteos nuevos desde LoteríaYa (páginas públicas de resultados).

Estado honesto: el análisis del formato se hizo con las páginas de octubre de 2026 (frase "…(sorteo 4857) fue 1271,
serie 087." y tabla "Seco | Número | Serie"). El código se probó contra una copia sintética de ese formato
(tests/fixtures), NO contra el sitio en vivo, porque el entorno donde se escribió no tenía salida a internet.
Si el sitio cambia, la descarga falla de forma controlada: se anota en el reporte y el resto del sistema sigue con
los datos que ya tiene y con lo que usted suba a data/inbox/.
"""
from __future__ import annotations

import datetime as dt
import re
import time

import pandas as pd

from . import store as st
from .config import LOTERIAS, NOMBRE

BASE = "https://www.loteriaya.com.co"
URL_RES = BASE + "/loteria/{slug}/resultado/{fecha}"
URL_LOT = BASE + "/loteria/{slug}"
HEADERS = {"User-Agent": "ATLAS-estadistica/1.0 (proyecto personal de investigación; 1 solicitud cada 2 s)"}
META = re.compile(r"\(sorteo\s+(\d+)\)\s+fue\s+(\d{4}),\s*serie\s+(\d{3})", re.I)
FILA = re.compile(r"Seco\s*\d+\D{0,40}?(\d{4})\D{1,40}?(\d{3})(?!\d)", re.I)


def parsear(html: str) -> dict:
    """Extrae mayor y secos de una página de resultado. Lanza ValueError si no reconoce el formato."""
    m = META.search(html)
    if not m:
        raise ValueError("no aparece la frase del número ganador (¿sorteo no publicado aún o formato cambiado?)")
    sorteo, num, ser = m.groups()
    secos = []
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        for tabla in soup.find_all("table"):
            enc = [c.get_text(" ", strip=True).lower() for c in tabla.find_all("th")]
            if not enc:
                primera = tabla.find("tr")
                enc = [c.get_text(" ", strip=True).lower() for c in primera.find_all(["td", "th"])] if primera else []
            if any("mero" in e for e in enc) and any("serie" in e for e in enc):
                i_num = next(i for i, e in enumerate(enc) if "mero" in e)
                i_ser = next(i for i, e in enumerate(enc) if "serie" in e)
                for tr in tabla.find_all("tr"):
                    celdas = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
                    if len(celdas) > max(i_num, i_ser) and re.fullmatch(r"\d{4}", celdas[i_num]):
                        s = celdas[i_ser]
                        secos.append((celdas[i_num], s if re.fullmatch(r"\d{3}", s) else ""))
                if secos:
                    break
    except ImportError:
        pass
    if not secos:  # respaldo por texto plano
        texto = re.sub(r"<[^>]+>", " ", html)
        secos = FILA.findall(texto)
    return dict(sorteo=sorteo, numero=num, serie=ser, secos=secos)


def fechas_publicadas(html: str, slug: str) -> list[str]:
    return sorted(set(re.findall(rf"/loteria/{re.escape(slug)}/resultado/(\d{{4}}-\d{{2}}-\d{{2}})", html)))


def candidatos(store: pd.DataFrame, hoy: dt.date, dias_atras: int = 21) -> list[tuple[str, str]]:
    """Sorteos que probablemente ya se publicaron y aún no tienen secos en el almacén.

    - Solo fechas anteriores a hoy (los sorteos son de noche).
    - Se aceptan corrimientos por festivo (día de juego y los 3 siguientes).
    - Si ya hay premio mayor y pasaron más de 3 días, se asume que la fuente no publicó secos y no se insiste."""
    tiene = set(zip(store[store.tipo == "seco"].slug, store[store.tipo == "seco"].fecha))
    mayor = set(zip(store[store.tipo == "mayor"].slug, store[store.tipo == "mayor"].fecha))
    out = []
    for slug, (_, wd, _) in LOTERIAS.items():
        for k in range(dias_atras, 0, -1):
            d = hoy - dt.timedelta(days=k)
            if d.weekday() != wd:
                continue
            ventana = [(slug, (d + dt.timedelta(days=j)).isoformat()) for j in range(4)]
            if any(v in tiene for v in ventana):
                continue
            if k > 3 and any(v in mayor for v in ventana):
                continue
            out.append((slug, d.isoformat()))
    return out


def descargar(store: pd.DataFrame, hoy: dt.date | None = None, max_paginas: int = 60, pausa: float = 2.0,
              obtener=None) -> tuple[pd.DataFrame, dict]:
    """Descarga los sorteos faltantes. `obtener(url)->html` permite inyectar un cliente simulado en las pruebas."""
    hoy = hoy or dt.datetime.now(dt.timezone(dt.timedelta(hours=-5))).date()
    info = dict(intentos=0, sorteos_nuevos=0, errores=[], estado="ok")
    if obtener is None:
        try:
            import requests
        except ImportError:
            info.update(estado="sin requests"); return store, info
        ses = requests.Session(); ses.headers.update(HEADERS)

        def obtener(url):
            r = ses.get(url, timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.text
    rep = st.Reporte()
    pend = candidatos(store, hoy)
    por_lot: dict[str, list[str]] = {}
    for slug, f in pend:
        por_lot.setdefault(slug, []).append(f)
    nuevas = []
    for slug, fechas in por_lot.items():
        if info["intentos"] >= max_paginas:
            break
        # 1) intentar descubrir las fechas reales publicadas en la página de la lotería
        reales = []
        try:
            info["intentos"] += 1
            html = obtener(URL_LOT.format(slug=slug))
            reales = fechas_publicadas(html or "", slug)
            time.sleep(pausa)
        except Exception as e:  # noqa: BLE001
            info["errores"].append(f"{NOMBRE[slug]}: página principal no disponible ({type(e).__name__}: {e})"[:300])
        objetivo = []
        for f in fechas:
            d = dt.date.fromisoformat(f)
            ventana = [(d + dt.timedelta(days=j)).isoformat() for j in range(4)]
            hit = [x for x in ventana if x in reales]
            objetivo += hit[:1] if hit else ([] if reales else [f])   # sin lista: probar el día de juego
        for f in objetivo:
            if info["intentos"] >= max_paginas or f >= hoy.isoformat():
                continue
            url = URL_RES.format(slug=slug, fecha=f)
            try:
                info["intentos"] += 1
                html = obtener(url)
                time.sleep(pausa)
                if not html:
                    continue
                p = parsear(html)
            except Exception as e:  # noqa: BLE001
                info["errores"].append(f"{NOMBRE[slug]} {f}: {type(e).__name__}: {e}"[:300]); continue
            nuevas.append(dict(slug=slug, fecha=f, sorteo=p["sorteo"], tipo="mayor", numero=p["numero"],
                               serie=p["serie"], fuente="LoteríaYa", url=url))
            for i, (n, s) in enumerate(p["secos"], 1):
                nuevas.append(dict(slug=slug, fecha=f, sorteo=p["sorteo"], tipo="seco", fila=str(i), numero=n,
                                   serie=s, fuente="LoteríaYa", url=url))
            info["sorteos_nuevos"] += 1
            if not p["secos"]:
                info["errores"].append(f"{NOMBRE[slug]} {f}: LoteríaYa publicó el premio mayor pero no la lista de secos "
                                       "(puede agregarla a mano)")
    if nuevas:
        store = st.incorporar(store, pd.DataFrame(nuevas), rep)
    info["reporte"] = rep.dict()
    if info["errores"] and not info["sorteos_nuevos"]:
        info["estado"] = "fallo" if info["intentos"] else "sin conexión"
    return store, info
