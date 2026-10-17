"""Almacén único de resultados (data/store/resultados.csv) y reglas para incorporar datos nuevos sin duplicar.

Una fila por premio publicado:
  slug, fecha, sorteo, tipo (mayor|seco), fila, numero, serie, cuantia_millones, fuente, fuente_cuantia, url,
  ingresado_en, nota
Los números y las series SIEMPRE son texto ("0047", "003").
"""
from __future__ import annotations

import datetime as dt
import glob
import os

import pandas as pd

from .config import STORE, RAIZ, NOMBRE

COLS = ["slug", "fecha", "sorteo", "tipo", "fila", "numero", "serie", "cuantia_millones", "fuente",
        "fuente_cuantia", "url", "ingresado_en", "nota"]
LY_URL = "https://www.loteriaya.com.co/loteria/{slug}/resultado/{fecha}"


def ahora() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=-5))).isoformat(timespec="seconds")


def vacio() -> pd.DataFrame:
    return pd.DataFrame(columns=COLS)


def cargar() -> pd.DataFrame:
    if not os.path.exists(STORE):
        return vacio()
    df = pd.read_csv(STORE, dtype=str, keep_default_na=False)
    for c in COLS:
        if c not in df:
            df[c] = ""
    return df[COLS]


def guardar(df: pd.DataFrame) -> None:
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    df = df[COLS].copy()
    df["_f"] = pd.to_numeric(df.fila, errors="coerce")
    df = df.sort_values(["fecha", "slug", "tipo", "_f", "numero"], na_position="last").drop(columns="_f")
    df.to_csv(STORE, index=False)


class Reporte:
    def __init__(self):
        self.agregadas = 0; self.cuantias = 0; self.sin_cambio = 0
        self.conflictos: list[str] = []; self.avisos: list[str] = []

    def dict(self):
        return dict(filas_agregadas=self.agregadas, cuantias_completadas=self.cuantias, sin_cambio=self.sin_cambio,
                    conflictos=self.conflictos[:200], avisos=self.avisos[:200])


def incorporar(store: pd.DataFrame, nuevas: pd.DataFrame, rep: Reporte) -> pd.DataFrame:
    """Une filas nuevas (ya validadas) al almacén.

    - Mayor: una por (lotería, fecha). Si llega distinto al guardado, se registra conflicto y se conserva el guardado.
    - Secos de un sorteo que aún no tiene secos: se agregan todos, numerados en el orden recibido.
    - Secos de un sorteo que ya tiene lista: solo completan la cuantía de las filas que coinciden en número y serie;
      los que no coinciden se agregan con nota (pueden ser premios que la primera fuente omitió).
    """
    store = store.copy()
    nuevas = nuevas.fillna("")
    for c in COLS:
        if c not in nuevas:
            nuevas[c] = ""
    agregar = []
    for (slug, fecha), g in nuevas.groupby(["slug", "fecha"], sort=False):
        en_store = store[(store.slug == slug) & (store.fecha == fecha)]
        # ---- mayor
        for _, r in g[g.tipo == "mayor"].iterrows():
            m = en_store[en_store.tipo == "mayor"]
            if m.empty:
                agregar.append(r); rep.agregadas += 1
            else:
                old = m.iloc[0]
                if (old.numero, old.serie) == (r.numero, r.serie):
                    rep.sin_cambio += 1
                elif old.serie == "" and old.numero == r.numero and r.serie:
                    store.loc[m.index[0], "serie"] = r.serie; rep.cuantias += 0
                else:
                    rep.conflictos.append(f"{NOMBRE.get(slug, slug)} {fecha}: mayor guardado {old.numero}/{old.serie}, "
                                          f"nuevo {r.numero}/{r.serie} ({r.fuente}). Se conserva el guardado.")
        # ---- secos
        s_new = g[g.tipo == "seco"]
        if s_new.empty:
            continue
        s_old = en_store[en_store.tipo == "seco"]
        if s_old.empty:
            s_new = s_new.copy()
            filas = pd.to_numeric(s_new.fila, errors="coerce")
            if filas.isna().any():
                s_new["fila"] = [str(i) for i in range(1, len(s_new) + 1)]
            dup = s_new.duplicated(["numero", "serie"], keep=False)
            if dup.any():
                rep.avisos.append(f"{NOMBRE.get(slug, slug)} {fecha}: {int(dup.sum())} filas repiten número y serie; "
                                  "se guardan y el análisis las marca como duplicado.")
            agregar.extend(r for _, r in s_new.iterrows()); rep.agregadas += len(s_new)
            continue
        maxfila = pd.to_numeric(s_old.fila, errors="coerce").max()
        maxfila = 0 if pd.isna(maxfila) else int(maxfila)
        for _, r in s_new.iterrows():
            hit = s_old[(s_old.numero == r.numero) & (s_old.serie == r.serie)]
            if hit.empty:
                r = r.copy(); r["nota"] = (r.nota + "; " if r.nota else "") + "agregado a una lista ya existente"
                r["fila"] = ""
                agregar.append(r); rep.agregadas += 1
                rep.avisos.append(f"{NOMBRE.get(slug, slug)} {fecha}: {r.numero}/{r.serie} no estaba en la lista guardada.")
                continue
            i = hit.index[0]
            if r.cuantia_millones:
                old = store.at[i, "cuantia_millones"]
                if not old:
                    store.at[i, "cuantia_millones"] = r.cuantia_millones
                    store.at[i, "fuente_cuantia"] = r.fuente_cuantia or r.fuente
                    rep.cuantias += 1
                elif str(float(old)) != str(float(r.cuantia_millones)):
                    rep.conflictos.append(f"{NOMBRE.get(slug, slug)} {fecha}: {r.numero}/{r.serie} cuantía guardada "
                                          f"{old}, nueva {r.cuantia_millones}. Se conserva la guardada.")
                else:
                    rep.sin_cambio += 1
            else:
                rep.sin_cambio += 1
    if agregar:
        add = pd.DataFrame(agregar)[COLS]
        add["ingresado_en"] = add.ingresado_en.where(add.ingresado_en != "", ahora())
        store = pd.concat([store, add], ignore_index=True)
    return store


# ------------------------------------------------------------------ migración de los datos del estudio
def migrar_legado(escribir: bool = True):
    """Convierte los archivos del estudio (estudio/data/raw) al almacén único."""
    raw = os.path.join(RAIZ, "estudio", "data", "raw")
    rep = Reporte(); store = vacio(); t = "2026-10-17T10:00:00-05:00"
    filas = []
    for f in sorted(glob.glob(os.path.join(raw, "hist_*.csv"))):
        slug = os.path.basename(f)[5:-4]
        d = pd.read_csv(f, dtype=str, keep_default_na=False)
        for _, r in d[d.sorteo != "NODRAW"].iterrows():
            filas.append(dict(slug=slug, fecha=r.date, sorteo=r.sorteo, tipo="mayor", fila="", numero=r.number,
                              serie=r.series, fuente="LoteríaYa historial",
                              url=f"https://www.loteriaya.com.co/loteria/{slug}/historial", ingresado_en=t))
    store = incorporar(store, pd.DataFrame(filas), rep)
    filas = []
    for f in sorted(glob.glob(os.path.join(raw, "ly", "*.txt"))):
        slug, fecha = os.path.basename(f)[:-4].rsplit("_", 1)
        lines = [l.strip() for l in open(f, encoding="utf-8") if l.strip()]
        _, sorteo, num, ser = lines[0].split(",")
        url = LY_URL.format(slug=slug, fecha=fecha)
        filas.append(dict(slug=slug, fecha=fecha, sorteo=sorteo, tipo="mayor", numero=num, serie=ser,
                          fuente="LoteríaYa", url=url, ingresado_en=t))
        for i, l in enumerate(lines[1:], 1):
            p = l.split(",")
            filas.append(dict(slug=slug, fecha=fecha, sorteo=sorteo, tipo="seco", fila=str(i), numero=p[0],
                              serie=p[1] if len(p) > 1 else "", fuente="LoteríaYa", url=url, ingresado_en=t))
    store = incorporar(store, pd.DataFrame(filas), rep)
    fuentes = {"telemedellin": "Telemedellín", "vanguardia": "Vanguardia", "radionacional": "Radio Nacional",
               "rlc": "resultadosloteriascol.com", "bogotagov": "bogota.gov.co"}
    filas = []
    for f in sorted(glob.glob(os.path.join(raw, "labeled", "*.csv"))):
        b = os.path.basename(f)[:-4].replace("_PARTIAL", "")
        src, rest = b.split("_", 1); slug, fecha = rest.rsplit("_", 1)
        d = pd.read_csv(f, dtype=str)
        for _, r in d.iterrows():
            amt = r.amount_millions
            nota = ""
            if slug == "loteria-de-medellin" and fecha == "2026-09-25" and r.number in ("0840", "8629"):
                amt, nota = "1000", "cuantía corregida por el plan de premios (la fuente decía 100)"
            filas.append(dict(slug=slug, fecha=fecha, tipo="seco", numero=r.number, serie=r.series,
                              cuantia_millones=amt, fuente=fuentes[src], fuente_cuantia=fuentes[src], nota=nota,
                              ingresado_en=t))
    store = incorporar(store, pd.DataFrame(filas), rep)
    if escribir:
        guardar(store)
    return store, rep
