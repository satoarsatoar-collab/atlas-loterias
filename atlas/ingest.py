"""Ingesta de archivos que el usuario sube a data/inbox/ (CSV, o Excel si está instalado openpyxl).

Columnas aceptadas (mayúsculas, tildes y espacios no importan):
  loteria   (o: lotería, slug, nombre)            "Medellín", "loteria-de-medellin", "medellin"...
  fecha     (o: date, dia)                        2026-10-23 o 23/10/2026
  tipo      (o: premio, clase)                    mayor | seco   (vacío = seco)
  numero    (o: número, billete, num)             "0047" — si Excel lo dejó en 47 se rellena a 0047 y se avisa
  serie                                            "003"  — idem
  cuantia_millones (o: cuantia, valor, premio_millones)   10, 40, "$10.000.000", "10 millones"
  fuente, sorteo, url                              opcionales
Las filas con problemas no se descartan en silencio: van al reporte con el motivo.
"""
from __future__ import annotations

import datetime as dt
import glob
import os
import re
import shutil

import pandas as pd

from . import store as st
from .config import INBOX, PROCESADOS, NOMBRE, normalizar_texto, slug_de

SINONIMOS = {
    "loteria": "loteria", "slug": "loteria", "nombre": "loteria", "loteria slug": "loteria", "lottery": "loteria",
    "fecha": "fecha", "date": "fecha", "dia": "fecha", "fecha sorteo": "fecha",
    "tipo": "tipo", "premio": "tipo", "clase": "tipo", "tipo premio": "tipo",
    "numero": "numero", "billete": "numero", "num": "numero", "number": "numero", "resultado": "numero",
    "serie": "serie", "series": "serie",
    "cuantia millones": "cuantia_millones", "cuantia": "cuantia_millones", "valor": "cuantia_millones",
    "premio millones": "cuantia_millones", "valor millones": "cuantia_millones", "amount millions": "cuantia_millones",
    "fuente": "fuente", "source": "fuente", "sorteo": "sorteo", "numero sorteo": "sorteo", "url": "url",
}
TIPOS = {"mayor": "mayor", "premio mayor": "mayor", "m": "mayor", "seco": "seco", "secos": "seco", "s": "seco",
         "premio seco": "seco", "": "seco"}


def _fecha(x: str) -> str | None:
    x = str(x).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(x[:10] if fmt == "%Y-%m-%d" else x, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _digitos(x: str, n: int) -> tuple[str | None, bool]:
    x = str(x).strip()
    if re.fullmatch(r"\d+\.0", x):           # Excel convierte 47 en 47.0
        x = x[:-2]
    if not re.fullmatch(r"\d{1,%d}" % n, x):
        return None, False
    return x.zfill(n), len(x) < n


def _cuantia(x: str) -> str | None:
    x = normalizar_texto(x).replace("$", "").replace(" ", "")
    if not x:
        return ""
    mill = "millon" in x
    x = re.sub(r"[a-z]", "", x)
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", x):    # 10.000.000
        x = x.replace(".", "")
    x = x.replace(",", ".")
    try:
        v = float(x)
    except ValueError:
        return None
    if not mill and v >= 100000:                  # vino en pesos
        v /= 1e6
    return f"{v:g}"


def leer_archivo(path: str) -> pd.DataFrame:
    if path.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(path, dtype=str).fillna("")
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "latin-1"):
        try:
            txt = raw.decode(enc); break
        except UnicodeDecodeError:
            continue
    sep = ";" if txt.split("\n", 1)[0].count(";") > txt.split("\n", 1)[0].count(",") else ","
    from io import StringIO
    return pd.read_csv(StringIO(txt), dtype=str, sep=sep, keep_default_na=False)


def normalizar(df: pd.DataFrame, origen: str, hoy: dt.date | None = None) -> tuple[pd.DataFrame, list[dict], list[str]]:
    """Devuelve (filas válidas en formato del almacén, filas rechazadas con motivo, avisos)."""
    ren = {}
    for c in df.columns:
        k = SINONIMOS.get(normalizar_texto(c).replace("_", " "))
        if k and k not in ren.values():
            ren[c] = k
    df = df.rename(columns=ren).fillna("")
    faltan = [c for c in ("loteria", "fecha", "numero") if c not in df]
    if faltan:
        return pd.DataFrame(), [dict(archivo=origen, fila="-", motivo=f"faltan columnas: {', '.join(faltan)}")], []
    ok, malas, avisos, rellenos = [], [], [], 0
    limite = ((hoy or dt.date.today()) + dt.timedelta(days=1)).isoformat()
    for i, r in df.iterrows():
        fila = i + 2
        if not any(str(v).strip() for v in r.values):
            continue
        slug = slug_de(r.get("loteria", ""))
        fecha = _fecha(r.get("fecha", ""))
        tipo = TIPOS.get(normalizar_texto(r.get("tipo", "")))
        num, rn = _digitos(r.get("numero", ""), 4)
        ser_txt = str(r.get("serie", "")).strip()
        ser, rs = _digitos(ser_txt, 3) if ser_txt else ("", False)
        cu = _cuantia(r.get("cuantia_millones", ""))
        motivo = []
        if not slug: motivo.append(f"lotería desconocida «{r.get('loteria', '')}»")
        if not fecha: motivo.append(f"fecha ilegible «{r.get('fecha', '')}»")
        elif fecha > limite: motivo.append(f"fecha futura {fecha}")
        if not tipo: motivo.append(f"tipo desconocido «{r.get('tipo', '')}» (use mayor o seco)")
        if not num: motivo.append(f"número inválido «{r.get('numero', '')}»")
        if ser is None: motivo.append(f"serie inválida «{ser_txt}»")
        if cu is None: motivo.append(f"cuantía ilegible «{r.get('cuantia_millones', '')}»")
        if motivo:
            malas.append(dict(archivo=origen, fila=fila, motivo="; ".join(motivo)))
            continue
        rellenos += rn or rs
        ok.append(dict(slug=slug, fecha=fecha, sorteo=str(r.get("sorteo", "")).strip(), tipo=tipo, fila="",
                       numero=num, serie=ser, cuantia_millones=cu,
                       fuente=str(r.get("fuente", "")).strip() or f"carga manual ({origen})",
                       fuente_cuantia=(str(r.get("fuente", "")).strip() or f"carga manual ({origen})") if cu else "",
                       url=str(r.get("url", "")).strip(), ingresado_en=st.ahora(), nota=""))
    if rellenos:
        avisos.append(f"{origen}: {rellenos} números/series venían sin ceros a la izquierda (¿Excel?) y se rellenaron. "
                      "Revise que sean correctos: 47 se guardó como 0047.")
    out = pd.DataFrame(ok)
    if len(out):
        ser_vacia = (out.serie == "").sum()
        if ser_vacia:
            avisos.append(f"{origen}: {ser_vacia} filas sin serie; se guardan pero no entran al análisis de secos.")
    return out, malas, avisos


def procesar_inbox(store: pd.DataFrame, inbox: str = INBOX, procesados: str = PROCESADOS, hoy: dt.date | None = None):
    rep = st.Reporte(); rechazos = []; archivos = []
    for path in sorted(glob.glob(os.path.join(inbox, "*"))):
        nombre = os.path.basename(path)
        if nombre.startswith((".", "_")) or nombre.lower().endswith(".md") or nombre.lower() == "plantilla_resultados.csv":
            continue
        if not nombre.lower().endswith((".csv", ".txt", ".xlsx", ".xls")):
            rechazos.append(dict(archivo=nombre, fila="-", motivo="formato no admitido (use .csv o .xlsx)")); continue
        try:
            df = leer_archivo(path)
        except Exception as e:  # noqa: BLE001
            rechazos.append(dict(archivo=nombre, fila="-", motivo=f"no se pudo leer: {e}")); continue
        ok, malas, avisos = normalizar(df, nombre, hoy)
        rechazos += malas; rep.avisos += avisos
        if len(ok):
            store = st.incorporar(store, ok, rep)
        archivos.append(dict(archivo=nombre, filas_leidas=len(df), validas=len(ok), rechazadas=len(malas)))
        os.makedirs(procesados, exist_ok=True)
        sello = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.move(path, os.path.join(procesados, f"{sello}_{nombre}"))
    return store, rep, rechazos, archivos


PLANTILLA = """loteria,fecha,tipo,numero,serie,cuantia_millones,fuente,sorteo
Medellín,2026-10-23,mayor,0123,045,,Lotería de Medellín,
Medellín,2026-10-23,seco,0047,003,10,Telemedellín,
Medellín,2026-10-23,seco,5821,190,10,Telemedellín,
"""
