"""
PROYECTO ATLAS - Paso 6: protocolo prospectivo (pre-registro) y evaluación secuencial.

Uso:
  python prospective.py registrar          -> crea out/preregistro_<fecha>.json (+ huella SHA-256) con las predicciones
                                              de los próximos sorteos, usando SOLO datos ya publicados.
  python prospective.py evaluar <csv>      -> compara el pre-registro con resultados nuevos (CSV con columnas
                                              loteria_slug,fecha,tipo{mayor|seco},numero,serie[,cuantia_millones])

Por qué e-valores: permiten revisar los resultados cada semana sin inflar falsos positivos (desigualdad de Ville).
Para una predicción q y el nulo uniforme u, E = prod q(x)/u(x) es una martingala bajo H0; si en algún momento
E >= 1/alfa se rechaza H0 con error tipo I <= alfa, sin importar cuántas veces se mire.
"""
import sys, json, hashlib, datetime as dt
import numpy as np, pandas as pd
from common import *
from scipy import stats

ALPHA = 0.05
SCHEDULE = {  # día de juego (0 = lunes)
    "loteria-de-cundinamarca": 0, "loteria-del-tolima": 0, "loteria-de-la-cruz-roja": 1, "loteria-del-huila": 1,
    "loteria-de-manizales": 2, "loteria-del-meta": 2, "loteria-del-valle": 2, "loteria-de-bogota": 3,
    "loteria-del-quindio": 3, "loteria-de-medellin": 4, "loteria-de-risaralda": 4, "loteria-de-santander": 4,
    "loteria-de-boyaca": 5, "loteria-del-cauca": 5}
# Festivos que afectan el calendario de noviembre-diciembre 2026 (los sorteos de lunes pasan al martes, etc.).
FESTIVOS_2026 = ["2026-11-02", "2026-11-16", "2026-12-08", "2026-12-25"]

HIPOTESIS = [
    dict(id="H0-PRIMARIA", tipo="secuencial",
         enunciado="Ningún modelo predice la última cifra de los secos mejor que el azar uniforme.",
         prueba="E-valor de la mezcla de modelos (promedio de E de M1..M7) sobre la última cifra de cada seco independiente; "
                "se rechaza H0 si E >= 20 en cualquier momento (alfa = 0,05, válido con revisión continua).",
         prediccion_si_hay_senal="E crece de forma sostenida; con azar puro E tiende a 0."),
    dict(id="H1-MENOR-CUANTIA-4", tipo="binomial",
         enunciado="Entre los secos de MENOR cuantía (Medellín $10M, Manizales $40M, Boyacá $10M), la última cifra 4 sale "
                   "con probabilidad > 0,10.",
         origen="Patrón post hoc: 44 de 276 (15,9 %) en 17-ago..16-oct; no superó la confirmación formal.",
         prueba="Binomial unilateral, alfa = 0,01, con los primeros 400 secos de menor cuantía publicados después del "
                "17-oct-2026 (≈ 7 semanas). Se usa solo información posterior al registro.",
         como_se_refuta="Si la proporción observada es <= 0,12 o el p-valor >= 0,01, la hipótesis se descarta."),
    dict(id="H2-MAYORES-MISMO-DIA", tipo="binomial",
         enunciado="Los premios mayores de loterías que juegan el mismo día comparten la última cifra con probabilidad > 0,10.",
         origen="Historial: 123/999 = 12,3 % (p = 0,018 sin corregir; no significativo tras corrección múltiple).",
         prueba="Binomial unilateral, alfa = 0,01, con las primeras 300 parejas del mismo día posteriores al 17-oct-2026.",
         como_se_refuta="Proporción <= 0,11 o p >= 0,01."),
    dict(id="H3-TERMINACIONES-MISMO-DIA", tipo="poisson",
         enunciado="Los secos de loterías del mismo día comparten terminaciones de 2 cifras más que lo esperado (|A||B|/100).",
         origen="Exploración: +8 % (p = 0,0035); confirmación: no se sostuvo (p = 0,45).",
         prueba="Razón observado/esperado acumulada en 8 semanas; prueba de Poisson unilateral, alfa = 0,01.",
         como_se_refuta="Razón <= 1,03 o p >= 0,01."),
]


def next_draw_dates(start, weeks=2):
    rows = []
    d0 = pd.Timestamp(start)
    for k in range(7 * weeks):
        day = d0 + pd.Timedelta(days=k)
        for slug, wd in SCHEDULE.items():
            if day.weekday() == wd:
                f = day
                while f.strftime("%Y-%m-%d") in FESTIVOS_2026: f += pd.Timedelta(days=1)
                rows.append((slug, f.strftime("%Y-%m-%d")))
    return rows


def model_probs(values_by_lot, slug, prev_mayor_last=None, cond=None):
    allv = np.concatenate([np.array(v, int) for v in values_by_lot.values()])
    lc = np.bincount(np.array(values_by_lot.get(slug, []), int), minlength=10)
    pg = (np.bincount(allv, minlength=10) + 1) / (len(allv) + 10)
    lst = values_by_lot.get(slug, [])
    hc = np.bincount(np.array(lst[-150:], int), minlength=10)
    cold = (hc.max() + 1 - hc).astype(float)
    out = {"M0_uniforme": np.ones(10) / 10, "M1_frec_loteria": (lc + 1) / (lc.sum() + 10), "M2_frec_global": pg,
           "M3_dirichlet20": (lc + 20) / (lc.sum() + 200), "M4_jerarquico": (lc + 50 * pg) / (lc.sum() + 50),
           "M5_caliente": (hc + 1) / (hc.sum() + 10), "M6_fria": cold / cold.sum()}
    if cond is not None and prev_mayor_last is not None:
        row = cond[prev_mayor_last] + 1; out["M7_cond_mayor_previo"] = row / row.sum()
    return {k: [round(float(x), 6) for x in v] for k, v in out.items()}


def registrar():
    may, sec = load()
    S = sec[sec.clase == "seco"]
    last_date = max(S.fecha.max(), may.fecha.max())
    start = (pd.Timestamp(last_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    vals = {s: g.sort_values(["fecha", "fila"]).numero.str[-1].astype(int).tolist() for s, g in S.groupby("slug")}
    # condicional: última cifra del mayor anterior -> últimas cifras de los secos del sorteo siguiente
    cond = np.zeros((10, 10)); mm = may.set_index(["slug", "fecha"]).numero.to_dict()
    for s, g in S.groupby("slug"):
        fechas = sorted(g.fecha.unique())
        for a, b in zip(fechas[:-1], fechas[1:]):
            pm = int(mm.get((s, a), "0000")[-1])
            for v in g[g.fecha == b].numero.str[-1].astype(int): cond[pm, v] += 1
    preds = []
    for slug, fecha in next_draw_dates(start, weeks=2):
        last_m = may[may.slug == slug].sort_values("fecha").numero.iloc[-1]
        preds.append(dict(loteria=slug, fecha=fecha, objetivo="última cifra de cada seco",
                          probabilidades=model_probs(vals, slug, int(last_m[-1]), cond)))
    reg = dict(proyecto="ATLAS", creado=dt.datetime.now(dt.timezone(dt.timedelta(hours=-5))).isoformat(timespec="seconds"),
               datos_hasta=last_date, alfa=ALPHA, hipotesis=HIPOTESIS, predicciones=preds,
               regla_de_decision="Ver cada hipótesis. Ningún resultado se declara 'descubrimiento' fuera de estas reglas.")
    body = json.dumps(reg, ensure_ascii=False, sort_keys=True, indent=1)
    h = hashlib.sha256(body.encode()).hexdigest()
    path = f"{OUT}/preregistro_{start}.json"
    open(path, "w").write(body); open(path + ".sha256", "w").write(h + "\n")
    print(f"Pre-registro: {path}\nSHA-256: {h}\nSorteos cubiertos: {len(preds)} ({preds[0]['fecha']} .. {preds[-1]['fecha']})")
    return path, h


def evaluar(prereg_path, results_csv):
    reg = json.load(open(prereg_path)); new = pd.read_csv(results_csv, dtype=str)
    after = new[new.fecha > reg["datos_hasta"]]
    secos = after[after.tipo == "seco"]
    # --- H0: e-valores secuenciales
    P = {(p["loteria"], p["fecha"]): p["probabilidades"] for p in reg["predicciones"]}
    models = [m for m in next(iter(P.values())) if m != "M0_uniforme"]
    logE = {m: 0.0 for m in models}; n = 0
    for _, r in secos.sort_values(["fecha", "loteria_slug"]).iterrows():
        pr = P.get((r.loteria_slug, r.fecha))
        if pr is None: continue
        x = int(r.numero[-1]); n += 1
        for m in models:
            if m in pr: logE[m] += np.log(pr[m][x] / 0.1)
    E_mix = float(np.mean([np.exp(v) for v in logE.values()])) if n else 1.0
    out = {"H0-PRIMARIA": dict(secos_evaluados=n, E_por_modelo={m: float(np.exp(v)) for m, v in logE.items()},
                               E_mezcla=E_mix, rechaza_H0=E_mix >= 1 / ALPHA)}
    # --- H1: menor cuantía
    menor = {"loteria-de-medellin": "10", "loteria-de-manizales": "40", "loteria-de-boyaca": "10"}
    if "cuantia_millones" in secos:
        m = secos[secos.apply(lambda r: menor.get(r.loteria_slug) == str(r.get("cuantia_millones")), axis=1)].head(400)
        k = int((m.numero.str[-1] == "4").sum()); nn = len(m)
        out["H1-MENOR-CUANTIA-4"] = dict(n=nn, k=k, prop=k / nn if nn else None,
                                         p=float(stats.binomtest(k, nn, 0.1, alternative="greater").pvalue) if nn else None,
                                         completa=nn >= 400)
    # --- H2: mayores mismo día
    M = after[after.tipo == "mayor"]; k = t = 0
    for f, g in M.groupby("fecha"):
        v = g.numero.str[-1].tolist()
        for i in range(len(v)):
            for j in range(i + 1, len(v)): t += 1; k += v[i] == v[j]
    out["H2-MAYORES-MISMO-DIA"] = dict(parejas=t, coincidencias=k,
                                       p=float(stats.binomtest(k, t, 0.1, alternative="greater").pvalue) if t else None,
                                       completa=t >= 300)
    # --- H3: terminaciones de 2 cifras compartidas entre secos de loterías del mismo día
    o = e = 0
    for f, g in secos.groupby("fecha"):
        sets = [set(x.numero.str[-2:]) for _, x in g.groupby("loteria_slug")]
        for i in range(len(sets)):
            for j in range(i + 1, len(sets)):
                o += len(sets[i] & sets[j]); e += len(sets[i]) * len(sets[j]) / 100
    semanas = (pd.to_datetime(secos.fecha).max() - pd.Timestamp(reg["datos_hasta"])).days / 7 if len(secos) else 0
    out["H3-TERMINACIONES-MISMO-DIA"] = dict(observado=int(o), esperado=round(e, 2), razon=o / e if e else None,
                                             p=float(stats.poisson.sf(o - 1, e)) if e else None, completa=semanas >= 8)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "evaluar":
        evaluar(sys.argv[2], sys.argv[3])
    else:
        registrar()
