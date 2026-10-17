"""Auditoría: convierte el almacén en tablas de análisis (mayores, secos clasificados, cobertura, bitácora).

Misma lógica que el estudio original (estudio/src/build_dataset.py), pero leyendo el almacén único.
Una fila publicada como "seco" se excluye del análisis si no es una extracción independiente:
  derivado_permutacion_mayor  misma serie que el mayor y mismos dígitos en otro orden
  derivado_mayor_pm1          misma serie que el mayor y número = mayor ± 1
  derivado_permutacion_seco   misma serie y mismos dígitos que un seco anterior del mismo sorteo
  duplicado_en_sorteo         número y serie idénticos a otra fila del mismo sorteo
  serie_000_ambigua           serie 000 (una segunda fuente la excluye sistemáticamente)
  serie_faltante / invalido   fila incompleta o mal formada
  sin_confirmar               aparece solo en una fuente secundaria que llegó después de la lista principal
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re

import numpy as np
import pandas as pd

from .config import LOTERIAS, NOMBRE, INICIO_PROSPECTIVO, STATE, es_festivo

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
REPLICACION = {"loteria-de-bogota"}       # cuantías de Bogotá: conjunto de replicación del estudio
INICIO_SECOS = "2026-08-17"               # primer sorteo con secos en el estudio


def _is4(x): return isinstance(x, str) and re.fullmatch(r"\d{4}", x) is not None
def _is3(x): return isinstance(x, str) and re.fullmatch(r"\d{3}", x) is not None
def _key(n): return "".join(sorted(n))


def construir(store: pd.DataFrame) -> dict:
    audit = []

    def log(tipo, slug, fecha, detalle):
        audit.append(dict(tipo=tipo, loteria=NOMBRE.get(slug, slug), fecha=fecha, detalle=detalle))

    # ------------------------------------------------------------- mayores
    may = store[store.tipo == "mayor"].copy()
    may = may.sort_values(["fecha", "slug"]).drop_duplicates(["slug", "fecha"]).reset_index(drop=True)
    may["loteria"] = may.slug.map(NOMBRE)
    estado = []
    for _, r in may.iterrows():
        probs = []
        if not _is4(r.numero): probs.append("numero_invalido")
        if not _is3(r.serie): probs.append("serie_faltante")
        wd = dt.date.fromisoformat(r.fecha).weekday()
        if r.slug in LOTERIAS and wd != LOTERIAS[r.slug][1]:
            probs.append(f"dia_atipico({DIAS[wd]})")
        if probs:
            log("mayor_" + probs[0].split("(")[0], r.slug, r.fecha, f"{r.numero}/{r.serie} sorteo {r.sorteo}: {';'.join(probs)}")
        estado.append(";".join(probs) or "ok")
    may["estado"] = estado
    for slug, g in may.groupby("slug"):
        s = pd.to_numeric(g.sorteo, errors="coerce")
        for _, r in g[s.duplicated(keep=False) & s.notna()].iterrows():
            log("sorteo_duplicado", slug, r.fecha, f"número de sorteo {r.sorteo} repetido")
        for (_, r), d in zip(g.iterrows(), s.diff()):
            if pd.notna(d) and d not in (0, 1):
                log("salto_numeracion", slug, r.fecha, f"sorteo {r.sorteo}: salto de {int(d)} respecto al anterior")
    may["fase"] = np.where(may.fecha >= INICIO_PROSPECTIVO, "prospectiva", "retrospectiva")
    mm = may.set_index(["slug", "fecha"])[["numero", "serie"]].to_dict("index")

    # ------------------------------------------------------------- secos
    S = store[store.tipo == "seco"].copy()
    S["_f"] = pd.to_numeric(S.fila, errors="coerce")
    S = S.sort_values(["fecha", "slug", "_f"], na_position="last")
    rows = []
    for (slug, fecha), g in S.groupby(["slug", "fecha"], sort=False):
        M = mm.get((slug, fecha), {})
        Mn, Ms = M.get("numero", ""), M.get("serie", "")
        if not Mn:
            log("secos_sin_mayor", slug, fecha, "Hay secos pero no premio mayor: no se pueden detectar derivados del mayor")
        grupos, exactos = {}, {}
        for k, r in enumerate(g.itertuples(index=False), 1):
            num, ser = r.numero, r.serie
            clase, nota = "seco", ""
            if not _is4(num):
                clase, nota = "invalido", "número mal formado"
            elif not _is3(ser):
                clase, nota = "serie_faltante", "fila sin serie"
            elif "agregado a una lista ya existente" in (r.nota or ""):
                clase, nota = "sin_confirmar", f"solo en {r.fuente}; la lista principal del sorteo no lo trae"
            elif _is4(Mn) and ser == Ms and _key(num) == _key(Mn) and num != Mn:
                clase, nota = "derivado_permutacion_mayor", f"permutación del mayor {Mn} con su serie"
            elif _is4(Mn) and ser == Ms and min((int(num) - int(Mn)) % 10000, (int(Mn) - int(num)) % 10000) == 1:
                clase, nota = "derivado_mayor_pm1", f"mayor {Mn} ±1 con su serie"
            elif (ser, _key(num)) in grupos and grupos[(ser, _key(num))] != num:
                clase, nota = "derivado_permutacion_seco", f"permutación del seco {grupos[(ser, _key(num))]} con la misma serie"
            elif (num, ser) in exactos:
                clase, nota = "duplicado_en_sorteo", f"repite la fila {exactos[(num, ser)]}"
            elif ser == "000":
                clase, nota = "serie_000_ambigua", "serie 000: en otras fuentes no figura como seco"
            if clase in ("seco", "serie_000_ambigua"):
                grupos.setdefault((ser, _key(num)), num)
            if clase not in ("invalido", "serie_faltante", "sin_confirmar"):
                exactos.setdefault((num, ser), k)
            if clase == "sin_confirmar":
                log("discrepancia_fuentes", slug, fecha, f"{num}/{ser} aparece en {r.fuente} y no en la lista principal")
            rows.append(dict(slug=slug, loteria=NOMBRE.get(slug, slug), fecha=fecha, sorteo=r.sorteo, mayor=Mn,
                             serie_mayor=Ms, fila=k, numero=num, serie=ser, clase=clase, nota=nota,
                             cuantia_millones=r.cuantia_millones, fuente=r.fuente, fuente_cuantia=r.fuente_cuantia,
                             url=r.url))
    cols = ["slug", "loteria", "fecha", "sorteo", "mayor", "serie_mayor", "fila", "numero", "serie", "clase", "nota",
            "cuantia_millones", "fuente", "fuente_cuantia", "url"]
    sec = pd.DataFrame(rows, columns=cols)
    sec["cuantia"] = pd.to_numeric(sec.cuantia_millones, errors="coerce")
    con_cuantia = set(zip(sec[sec.cuantia.notna()].slug, sec[sec.cuantia.notna()].fecha))
    sec["sorteo_con_cuantia"] = [(a, b) in con_cuantia for a, b in zip(sec.slug, sec.fecha)]
    for _, r in sec[sec.sorteo_con_cuantia & sec.cuantia.isna() & (sec.clase == "seco")].iterrows():
        log("seco_sin_confirmar", r.slug, r.fecha, f"{r.numero}/{r.serie} no figura en la fuente con cuantías")
    sec["verificacion"] = np.where(sec.cuantia.notna() & (sec.fuente != sec.fuente_cuantia), "dos fuentes", "una fuente")
    # rango de cuantía dentro de cada lotería (1 = la más baja observada)
    tiers = sec[sec.cuantia.notna()].groupby("slug").cuantia.apply(lambda x: sorted(set(x))).to_dict()
    sec["rango_cuantia"] = [tiers[s].index(c) + 1 if pd.notna(c) else np.nan for s, c in zip(sec.slug, sec.cuantia)]
    sec["menor_cuantia"] = sec.rango_cuantia == 1
    sec["conjunto_cuantia"] = np.select(
        [sec.cuantia.isna(), sec.fecha >= INICIO_PROSPECTIVO, sec.slug.isin(REPLICACION)],
        ["", "prospectivo", "replicación"], "formulación")
    sec["fase"] = np.where(sec.fecha >= INICIO_PROSPECTIVO, "prospectiva", "retrospectiva")

    # ------------------------------------------------------------- cobertura (sorteos esperados vs. obtenidos)
    hoy = dt.date.today()
    ultimo = max(store.fecha.max(), INICIO_SECOS) if len(store) else INICIO_SECOS
    fin = min(dt.date.fromisoformat(ultimo), hoy)
    cob, faltan = [], []
    sec_draws = set(zip(sec.slug, sec.fecha)); may_draws = set(zip(may.slug, may.fecha))
    for slug, (nombre, wd, _) in LOTERIAS.items():
        d = dt.date.fromisoformat(INICIO_SECOS)
        d += dt.timedelta(days=(wd - d.weekday()) % 7)
        esperados = m_ok = s_ok = 0
        while d <= fin:
            esperados += 1
            ventana = {(d + dt.timedelta(days=k)).isoformat() for k in range(-1, 4)}
            hm = any((slug, f) in may_draws for f in ventana)
            hs = any((slug, f) in sec_draws for f in ventana)
            m_ok += hm; s_ok += hs
            if not hs:
                faltan.append(dict(loteria=nombre, slug=slug, fecha_esperada=d.isoformat(), tiene_mayor=bool(hm),
                                   festivo=es_festivo(d)))
            d += dt.timedelta(days=7)
        g = sec[sec.slug == slug]
        cob.append(dict(loteria=nombre, slug=slug, dia=DIAS[wd], sorteos_esperados=esperados, con_mayor=int(m_ok),
                        con_secos=int(s_ok), cobertura_secos_pct=round(100 * s_ok / esperados, 1) if esperados else None,
                        filas_secos=len(g), secos_independientes=int((g.clase == "seco").sum()),
                        excluidos=int((g.clase != "seco").sum()),
                        sorteos_con_cuantia=len({f for (s_, f) in con_cuantia if s_ == slug}),
                        mayores_historial=int((may.slug == slug).sum()),
                        historial_desde=may[may.slug == slug].fecha.min() if (may.slug == slug).any() else "",
                        ultimo_dato=max(g.fecha.max() if len(g) else "", may[may.slug == slug].fecha.max()
                                        if (may.slug == slug).any() else "")))
    cob = pd.DataFrame(cob); faltan = pd.DataFrame(faltan, columns=["loteria", "slug", "fecha_esperada", "tiene_mayor", "festivo"])
    audit = pd.DataFrame(audit, columns=["tipo", "loteria", "fecha", "detalle"])
    resumen = dict(
        generado=dt.datetime.now(dt.timezone(dt.timedelta(hours=-5))).isoformat(timespec="seconds"),
        mayores=int(len(may)), mayores_prospectivos=int((may.fase == "prospectiva").sum()),
        sorteos_con_secos=int(sec.groupby(["slug", "fecha"]).ngroups) if len(sec) else 0,
        filas_secos=int(len(sec)), secos_independientes=int((sec.clase == "seco").sum()),
        secos_prospectivos=int(((sec.clase == "seco") & (sec.fase == "prospectiva")).sum()),
        secos_con_cuantia=int(sec.cuantia.notna().sum()), clases=sec.clase.value_counts().to_dict(),
        eventos_auditoria=audit.tipo.value_counts().to_dict(), sorteos_sin_secos=int(len(faltan)),
        ultimo_dato=ultimo,
    )
    return dict(mayores=may, secos=sec, cobertura=cob, faltantes=faltan, auditoria=audit, resumen=resumen)


def guardar(t: dict, carpeta: str = os.path.join(STATE, "auditoria")) -> None:
    os.makedirs(carpeta, exist_ok=True)
    for k in ("mayores", "secos", "cobertura", "faltantes", "auditoria"):
        t[k].to_csv(os.path.join(carpeta, f"{k}.csv"), index=False)
    json.dump(t["resumen"], open(os.path.join(carpeta, "resumen.json"), "w"), ensure_ascii=False, indent=1)
