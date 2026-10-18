"""Ciclo completo de ATLAS: descargar -> ingerir -> auditar -> buscar patrones -> predecir -> publicar tablero.

Uso:
  python -m atlas.pipeline                 # con descarga automática
  python -m atlas.pipeline --scrape no     # solo con lo que haya en data/inbox/
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import math
import os
import re
import traceback

import numpy as np
import pandas as pd

from . import build, ingest, patterns, preregistro, scrape, series, store
from .config import (ALFA_FDR, E_OBSERVACION, INBOX, INICIO_PROSPECTIVO, NOMBRE, RAIZ, SITE, STATE,
                     proximos_sorteos)

TZ = dt.timezone(dt.timedelta(hours=-5))


def _json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=_conv)


def _conv(o):
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, (np.floating,)): return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.bool_,)): return bool(o)
    if isinstance(o, (set, tuple)): return list(o)
    return str(o)


def _registro_predicciones(M, S, hoy, ahora):
    """Guarda las predicciones de los próximos sorteos ANTES de conocer el resultado (con huella SHA-256)."""
    ultimo = S.groupby("slug").fecha.max().to_dict() if len(S) else {}
    preds = []
    for slug, fecha in proximos_sorteos(hoy, dias=8):
        if fecha <= ultimo.get(slug, ""):
            continue
        for tipo in ("seco", "mayor"):
            p = M.predecir(tipo, slug, fecha)
            if tipo == "mayor":
                p["top_numeros"] = p["top_numeros"][:5]; p["prob_top_numeros"] = p["prob_top_numeros"][:5]
            preds.append(p)
    reg = dict(generado=ahora.isoformat(timespec="seconds"), datos_hasta=S.fecha.max() if len(S) else "",
               inicio_prospectivo=INICIO_PROSPECTIVO, nota="Predicciones generadas solo con datos anteriores a cada "
               "sorteo. Ninguna está validada mientras el tablero no diga lo contrario.", predicciones=preds)
    carpeta = os.path.join(STATE, "predicciones")
    os.makedirs(carpeta, exist_ok=True)
    path = os.path.join(carpeta, f"{hoy.isoformat()}.json")
    cuerpo = json.dumps(reg, ensure_ascii=False, sort_keys=True, indent=1, default=_conv)
    open(path, "w", encoding="utf-8").write(cuerpo)
    open(path + ".sha256", "w").write(hashlib.sha256(cuerpo.encode()).hexdigest() + "\n")
    return preds


def _evaluar_registro(secos, mayores):
    """Compara cada predicción guardada con el resultado real (usa la predicción más antigua de cada sorteo)."""
    vistos = {}
    for f in sorted(glob.glob(os.path.join(STATE, "predicciones", "*.json"))):
        try:
            reg = json.load(open(f, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        gen = reg.get("generado", "")
        for p in reg.get("predicciones", []):
            k = (p["slug"], p["fecha"], p["tipo"])
            if k not in vistos:
                vistos[k] = (gen, p)
    S = secos[secos.clase == "seco"]
    filas = []; filas_met = []
    for (slug, fecha, tipo), (gen, p) in vistos.items():
        d = dt.date.fromisoformat(fecha)
        cand = [(d + dt.timedelta(days=j)).isoformat() for j in (0, 1, 2, 3, -1)]
        base = S if tipo == "seco" else mayores
        g = None
        for c in cand:
            h = base[(base.slug == slug) & (base.fecha == c)]
            if len(h):
                g, real = h, c; break
        if g is None:
            continue
        if gen[:10] > real or (gen[:10] == real and gen[11:13] >= "19"):
            continue                              # se generó cuando el sorteo ya podía conocerse
        top = set(p["top_numeros"]); n = len(g)
        hits = g[g.numero.isin(top)].numero.tolist()
        u = p["ultima_cifra"][0]["cifra"]
        filas.append(dict(loteria=NOMBRE.get(slug, slug), slug=slug, fecha=real, tipo=tipo, predicho_el=gen,
                          premios=n, top=len(top), aciertos=len(hits), esperado_azar=n * len(top) / 1e4,
                          numeros_acertados=" ".join(hits), ultima_cifra_predicha=u,
                          aciertos_ultima_cifra=int((g.numero.str[-1] == str(u)).sum())))
        for met, lst in p.get("listas", {}).items():
            h = g[g.numero.isin(set(lst))].numero.tolist()
            filas_met.append(dict(slug=slug, fecha=real, metodo=met, premios=n, aciertos=len(h),
                                  esperado=n * len(set(lst)) / 1e4, numeros_acertados=" ".join(h)))
        if p.get("listas_series") and p.get("series_posibles"):
            S = p.get("series_en_juego", 1000)
            val = g[g.serie.astype(str).str.fullmatch(r"\d{3}") & (g.serie.astype(str) != "000")]
            val = val[val.serie.astype(int) < S]
            for met, lst in p["listas_series"].items():
                h = val[val.serie.isin(set(lst))].serie.tolist()
                filas_met.append(dict(slug=slug, fecha=real, metodo=met, premios=len(val), aciertos=len(h),
                                      esperado=len(val) * len(set(lst)) / p["series_posibles"], numeros_acertados=" ".join(h)))
    cols = ["loteria", "slug", "fecha", "tipo", "predicho_el", "premios", "top", "aciertos", "esperado_azar",
            "numeros_acertados", "ultima_cifra_predicha", "aciertos_ultima_cifra"]
    reg = pd.DataFrame(filas, columns=cols).sort_values(["fecha", "slug", "tipo"]) if filas else pd.DataFrame(columns=cols)
    met = pd.DataFrame(filas_met, columns=["slug", "fecha", "metodo", "premios", "aciertos", "esperado", "numeros_acertados"])
    return reg, met


def _marcador(met_motor: pd.DataFrame, met_reg: pd.DataFrame) -> list[dict]:
    """Aciertos de cada método de "números posibles": historial, datos nuevos y predicciones guardadas con huella."""
    def resumen(g):
        return dict(premios=int(g.premios.sum()), aciertos=int(g.aciertos.sum()), esperado=float(g.esperado.sum()),
                    numeros=" ".join(x for x in g.numeros_acertados if x)[:200])
    out = []
    for met, (nombre, desc) in {**patterns.METODOS, **patterns.METODOS_SERIE}.items():
        a = met_motor[met_motor.metodo == met]; b = met_reg[met_reg.metodo == met]
        out.append(dict(id=met, nombre=nombre, descripcion=desc, historial=resumen(a[~a.prospectivo.astype(bool)]),
                        nuevos=resumen(a[a.prospectivo.astype(bool)]), registrado=resumen(b)))
    return out


def _consulta(secos, mayores) -> dict:
    """Para el buscador de números: veces que salió cada número (secos independientes y mayores) y la última vez."""
    from .config import INICIO_SERIES
    Si = secos[secos.clase == "seco"]
    lots = sorted(Si.slug.unique())
    pares = {}
    for r in Si.itertuples():
        pares.setdefault(r.numero, []).append([lots.index(r.slug), r.serie])
    cuenta_series = {s: g[g.fecha >= INICIO_SERIES].serie.value_counts().to_dict() for s, g in Si.groupby("slug")}
    n_series = {s: int((g.fecha >= INICIO_SERIES).sum()) for s, g in Si.groupby("slug")}
    S = Si[["numero", "fecha", "loteria"]].assign(t="s")
    M = mayores[mayores.numero.str.fullmatch(r"\d{4}", na=False)][["numero", "fecha", "loteria"]].assign(t="m")
    A = pd.concat([S, M]).sort_values("fecha")
    out = {}
    for n, g in A.groupby("numero"):
        u = g.iloc[-1]
        out[n] = [int((g.t == "s").sum()), int((g.t == "m").sum()), u.fecha, u.loteria, u.t]
    return dict(numeros=out, secos_desde=S.fecha.min() if len(S) else "", mayores_desde=M.fecha.min() if len(M) else "",
                total_secos=int(len(S)), total_mayores=int(len(M)), lots=lots, nombres_lots=[NOMBRE.get(x, x) for x in lots],
                pares=pares, series=cuenta_series, n_series=n_series, series_desde=INICIO_SERIES)


def _economia():
    path = os.path.join(RAIZ, "estudio", "out", "economia_valor_esperado.csv")
    riesgo = os.path.join(RAIZ, "estudio", "out", "economia_riesgo.csv")
    out = []
    try:
        E = pd.read_csv(path)
        R = pd.read_csv(riesgo).set_index("loteria") if os.path.exists(riesgo) else pd.DataFrame()
        for lot in E.loteria.unique():
            r = E[E.loteria == lot].iloc[0]
            out.append(dict(loteria=lot, series=int(r.S_supuesto), precio=float(r.precio_billete),
                            ve_bruto=float(r.VE_bruto), ve_neto=float(r.VE_neto), retorno_neto_pct=float(r.retorno_neto_pct),
                            perdida=float(r.perdida_esperada_por_billete), prob_algun_premio=float(r.prob_algun_premio),
                            multiplicador_necesario=float(r.multiplicador_necesario),
                            prob_ganar_un_ano=float(R.loc[lot, "prob_terminar_ganando"]) if lot in R.index else None))
    except Exception:  # noqa: BLE001
        pass
    return out


def _fecha_txt(f):
    d = dt.date.fromisoformat(f)
    m = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"][d.month - 1]
    return f"{d.day} de {m} de {d.year}"


def _veredicto(res, principal, dias_p, n_p):
    if res["validados"]:
        return dict(nivel="senal", titulo="Un patrón superó la prueba en datos nuevos",
                    texto="Es la primera condición para tomarlo en serio, no la última: debe seguir sosteniéndose, "
                          "y aun siendo real tendría que multiplicar por más de 3 la probabilidad de ganar para que "
                          "comprar billetes deje de perder dinero en promedio.")
    if res["en_observacion"]:
        return dict(nivel="observacion", titulo="Hay patrones en observación, ninguno validado",
                    texto=f"Algún patrón superó E = {E_OBSERVACION:g} en datos nuevos. Con más de mil patrones vigilados "
                          "esto ocurre por azar con frecuencia; solo cuenta si pasa la corrección e-BH.")
    if n_p == 0:
        return dict(nivel="inicio", titulo="El seguimiento en datos nuevos empieza con el próximo sorteo",
                    texto=f"Desde el {_fecha_txt(INICIO_PROSPECTIVO)} cada patrón apuesta antes de cada sorteo. Lo anterior a esa "
                          "fecha ya se miró en el estudio y solo sirve de contexto.")
    miles = f"{n_p:,}".replace(",", ".")
    return dict(nivel="azar", titulo="Todo sigue siendo compatible con el azar",
                texto=f"Tras {dias_p} {'día' if dias_p == 1 else 'días'} y {miles} premios nuevos, ningún patrón ni "
                      "combinación le gana al azar de forma sostenida.")


def _repo() -> tuple[str, str]:
    """Repositorio de GitHub (dueño/nombre) y rama, para que el tablero arme el enlace de carga."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    rama = os.environ.get("GITHUB_REF_NAME", "") or "main"
    if not repo:
        try:
            import subprocess
            url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=RAIZ, capture_output=True, text=True,
                                 timeout=5).stdout.strip()
            m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", url)
            repo = m.group(1) if m else ""
        except Exception:  # noqa: BLE001
            repo = ""
    return repo, rama


def _recientes(secos, mayores, faltantes, hoy, dias=8) -> list[dict]:
    """Sorteos de los últimos días con lo que se tiene de cada uno, para confirmarlos o completarlos."""
    desde = (hoy - dt.timedelta(days=dias)).isoformat()
    M = mayores[mayores.fecha >= desde].set_index(["slug", "fecha"])
    S = secos[secos.fecha >= desde]
    claves = set(M.index) | set(zip(S.slug, S.fecha))
    out = []
    for slug, fecha in claves:
        g = S[(S.slug == slug) & (S.fecha == fecha)].sort_values("fila")
        m = M.loc[(slug, fecha)] if (slug, fecha) in M.index else None
        fuentes = sorted({f for f in list(g.fuente) + ([m.fuente] if m is not None else []) if f})
        out.append(dict(slug=slug, loteria=NOMBRE.get(slug, slug), fecha=fecha,
                        mayor=f"{m.numero}-{m.serie}" if m is not None else "", secos=int(len(g)),
                        independientes=int((g.clase == "seco").sum()), con_cuantia=int(g.cuantia.notna().sum()),
                        fuentes=fuentes, verificar=scrape.URL_RES.format(slug=slug, fecha=fecha),
                        lista=[[r.numero, r.serie, "" if pd.isna(r.cuantia) else f"{r.cuantia:g}", r.clase]
                               for r in g.itertuples()],
                        estado="completo" if (len(g) and m is not None) else ("sin secos" if m is not None else "sin mayor")))
    for r in faltantes.itertuples():
        if desde <= r.fecha_esperada < hoy.isoformat() and not r.tiene_mayor:
            out.append(dict(slug=r.slug, loteria=r.loteria, fecha=r.fecha_esperada, mayor="", secos=0, independientes=0,
                            con_cuantia=0, fuentes=[], verificar=scrape.URL_RES.format(slug=r.slug, fecha=r.fecha_esperada),
                            lista=[], estado="sin datos"))
    return sorted(out, key=lambda x: (x["fecha"], x["loteria"]), reverse=True)


def ejecutar(descargar: bool = True, hoy: dt.date | None = None) -> dict:
    ahora = dt.datetime.now(TZ)
    hoy = hoy or ahora.date()
    os.makedirs(STATE, exist_ok=True)
    previo = {}
    try:
        previo = json.load(open(os.path.join(SITE, "estado.json"), encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    S = store.cargar()
    migrado = False
    if S.empty and os.path.isdir(os.path.join(RAIZ, "estudio", "data", "raw")):
        S, _ = store.migrar_legado(); migrado = True
    info = dict(estado="omitida")
    if descargar:
        try:
            S, info = scrape.descargar(S, hoy=hoy)
        except Exception as e:  # noqa: BLE001
            info = dict(estado="fallo", errores=[f"{type(e).__name__}: {e}"], traza=traceback.format_exc()[-1500:])
    S, rep, rechazos, archivos = ingest.procesar_inbox(S, hoy=hoy)
    store.guardar(S)

    t = build.construir(S); build.guardar(t)
    M = patterns.Motor(t["mayores"], t["secos"]).correr()
    R = patterns.tablas(M)
    T = R["patrones"]
    T.to_csv(os.path.join(STATE, "patrones.csv"), index=False)
    R["aciertos"].to_csv(os.path.join(STATE, "aciertos_por_sorteo.csv"), index=False)
    preds = _registro_predicciones(M, S, hoy, ahora)
    reg, reg_met = _evaluar_registro(t["secos"], t["mayores"])
    reg.to_csv(os.path.join(STATE, "registro_aciertos.csv"), index=False)
    reg_met.to_csv(os.path.join(STATE, "registro_metodos.csv"), index=False)

    res = R["resumen"]
    prin = T[T.id == res["principal"]].iloc[0].to_dict() if (T.id == res["principal"]).any() else {}
    n_p = int(t["secos"].query("clase == 'seco' and fase == 'prospectiva'").shape[0]) + int(t["mayores"].query("fase == 'prospectiva'").shape[0])
    fechas_p = sorted(set(t["secos"].query("fase == 'prospectiva'").fecha) | set(t["mayores"].query("fase == 'prospectiva'").fecha))
    dias_p = (dt.date.fromisoformat(fechas_p[-1]) - dt.date.fromisoformat(INICIO_PROSPECTIVO)).days + 1 if fechas_p else 0

    # trayectorias: combinador principal + las 2 mejores reglas
    hay_p = n_p > 0
    col = "log10E_prosp" if hay_p else "log10E_total"
    reglas = T[T.clase == "regla"].sort_values(col, ascending=False)
    ids = [res["principal"]] + reglas.id.head(2).tolist()
    tr = patterns.trayectorias(M, ids)
    if hay_p:
        tr = tr[tr.fecha >= INICIO_PROSPECTIVO]
    nombres = {i: (T.set_index("id").descripcion.get(i, i)) for i in ids}
    vispera = (dt.date.fromisoformat(INICIO_PROSPECTIVO) - dt.timedelta(days=1)).isoformat()
    tray = [dict(id=i, nombre=nombres[i], puntos=([(vispera, 0.0)] if hay_p else []) +   # todas parten de E = 1
                 [(r.fecha, round(float(getattr(r, col)), 4)) for r in tr[tr.id == i].itertuples()]) for i in ids]

    ac = R["aciertos"]
    ac_s = ac[ac.tipo == "seco"].groupby("fecha")[["aciertos", "esperado"]].sum().cumsum().reset_index()
    resumen_ac = {}
    for fase, g in ac[ac.tipo == "seco"].groupby("prospectivo"):
        resumen_ac["prospectivo" if fase else "retrospectivo"] = dict(premios=int(g.premios.sum()),
                                                                     aciertos=int(g.aciertos.sum()),
                                                                     esperado=float(g.esperado.sum()))
    d4 = R["d4_top1"]
    d4s = {("prospectivo" if f else "retrospectivo"): dict(n=int(g.n.sum()), k=int(g.k.sum()))
           for f, g in d4[d4.tipo == "seco"].groupby("prospectivo")}

    hace28 = (hoy - dt.timedelta(days=28)).isoformat()
    falt = t["faltantes"]; falt = falt[falt.fecha_esperada >= hace28]
    estado = dict(
        generado=ahora.isoformat(timespec="seconds"), hoy=hoy.isoformat(), inicio_prospectivo=INICIO_PROSPECTIVO,
        dias_prospectivos=dias_p, premios_prospectivos=n_p, migrado_ahora=migrado,
        datos=t["resumen"], cobertura=t["cobertura"].to_dict("records"), faltantes_recientes=falt.to_dict("records"),
        auditoria=t["auditoria"].tipo.value_counts().to_dict(),
        conflictos=rep.conflictos + info.get("reporte", {}).get("conflictos", []),
        ingesta=dict(archivos=archivos, rechazos=rechazos[:200], avisos=rep.avisos[:100],
                     filas_agregadas=rep.agregadas, cuantias_completadas=rep.cuantias),
        descarga={k: v for k, v in info.items() if k != "traza"},
        motor=res, principal=prin, umbral_observacion=E_OBSERVACION, alfa=ALFA_FDR,
        top_patrones=T.head(30).to_dict("records"),
        peores_patrones=T[T.clase == "regla"].sort_values("log10E_total").head(5).to_dict("records"),
        trayectorias=dict(columna=col, series=tray),
        aciertos=resumen_ac, aciertos_serie=ac_s.to_dict("records"), ultima_cifra_top1=d4s,
        proximos=preds, registro=reg.to_dict("records")[-200:],
        registro_resumen=dict(sorteos=int(len(reg)), aciertos=int(reg.aciertos.sum()) if len(reg) else 0,
                              esperado=float(reg.esperado_azar.sum()) if len(reg) else 0.0),
        economia=_economia(),
        metodos=_marcador(R["metodos"], reg_met),
        series=series.analizar(M),
        series_en_juego={k: int(v) for k, v in M.S.items()},
        recientes=_recientes(t["secos"], t["mayores"], t["faltantes"], hoy),
        repo=_repo()[0], rama=_repo()[1],
        consulta=_consulta(t["secos"], t["mayores"]),
    )
    try:
        estado["preregistro"] = preregistro.evaluar(t["secos"], t["mayores"])
    except Exception as ex:  # noqa: BLE001
        estado["preregistro"] = dict(error=f"{type(ex).__name__}: {ex}")
    estado["veredicto"] = _veredicto(res, prin, dias_p, n_p)
    nuevos = sorted(set(res["validados"]) - set(previo.get("motor", {}).get("validados", [])))
    alerta = os.path.join(STATE, "alerta_nueva.md")
    if nuevos:
        lin = [f"# ATLAS: {len(nuevos)} patrón(es) nuevo(s) validado(s) — {hoy}", ""]
        for i in nuevos:
            r = T[T.id == i].iloc[0]
            lin.append(f"- **{r.descripcion}** — E prospectivo = {10 ** r.log10E_prosp:,.0f} con {r.premios_prospectivos} premios")
        lin += ["", "Validado significa que superó e-BH al 10 % entre todos los patrones vigilados. Revise el tablero "
                "antes de sacar conclusiones: un patrón real todavía tiene que vencer el margen de la lotería."]
        open(alerta, "w", encoding="utf-8").write("\n".join(lin) + "\n")
    elif os.path.exists(alerta):
        os.remove(alerta)
    from . import dashboard
    os.makedirs(SITE, exist_ok=True)
    _json(os.path.join(SITE, "estado.json"), estado)
    open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(dashboard.render(estado))
    open(os.path.join(STATE, "RESUMEN.md"), "w", encoding="utf-8").write(dashboard.render_md(estado))
    T.to_csv(os.path.join(SITE, "patrones.csv"), index=False)       # descarga desde el tablero
    plantilla = os.path.join(INBOX, "plantilla_resultados.csv")
    if not os.path.exists(plantilla):
        open(plantilla, "w", encoding="utf-8").write(ingest.PLANTILLA)
    return estado


def main():
    ap = argparse.ArgumentParser(description="Ejecuta el ciclo completo de ATLAS")
    ap.add_argument("--scrape", choices=["si", "no"], default="si", help="descargar resultados nuevos de internet")
    a = ap.parse_args()
    e = ejecutar(descargar=a.scrape == "si")
    d = e["datos"]; m = e["motor"]
    print(f"[ATLAS] {e['generado']} | último dato {d['ultimo_dato']} | secos independientes {d['secos_independientes']} "
          f"| mayores {d['mayores']} | descarga: {e['descarga'].get('estado')} ({e['descarga'].get('sorteos_nuevos', 0)} sorteos)")
    print(f"[ATLAS] patrones vigilados {m['reglas'] + m['combinadores']} | validados {len(m['validados'])} "
          f"| en observación {len(m['en_observacion'])} | veredicto: {e['veredicto']['titulo']}")
    if e["ingesta"]["rechazos"]:
        print(f"[ATLAS] filas rechazadas en la carga: {len(e['ingesta']['rechazos'])} (ver tablero)")


if __name__ == "__main__":
    main()
