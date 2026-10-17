"""Evaluación automática del pre-registro del estudio (estudio/out/preregistro_2026-10-17.json).

Las cuatro hipótesis y sus reglas de decisión se fijaron el 17-oct-2026, con huella SHA-256, antes de ver un solo
sorteo nuevo. Aquí solo se aplican tal cual. Se usan los secos independientes (los derivados se excluyen, como en el
estudio). Las pruebas binomial y de Poisson se calculan de forma exacta, sin dependencias externas.
"""
from __future__ import annotations

import hashlib
import json
import math
import os

import numpy as np
import pandas as pd

from .config import RAIZ

ARCHIVO = os.path.join(RAIZ, "estudio", "out", "preregistro_2026-10-17.json")
MENOR = {"loteria-de-medellin": 10.0, "loteria-de-manizales": 40.0, "loteria-de-boyaca": 10.0}


def binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k), X ~ Binomial(n, p)."""
    if n == 0:
        return 1.0
    return float(min(1.0, sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))))


def poisson_sf(k: int, lam: float) -> float:
    """P(X >= k), X ~ Poisson(lam)."""
    if k <= 0:
        return 1.0
    term = math.exp(-lam); cdf = term
    for i in range(1, k):
        term *= lam / i; cdf += term
    return float(max(0.0, 1 - cdf))


def _n(x, d=1):
    return f"{x:,.{d}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _p(x):
    return f"{x:.2g}".replace(".", ",") if x >= 1e-4 else "< 0,0001"


def evaluar(secos: pd.DataFrame, mayores: pd.DataFrame) -> dict | None:
    if not os.path.exists(ARCHIVO):
        return None
    cuerpo = open(ARCHIVO, encoding="utf-8").read()
    huella = hashlib.sha256(cuerpo.encode()).hexdigest()
    esperada = open(ARCHIVO + ".sha256").read().strip() if os.path.exists(ARCHIVO + ".sha256") else ""
    reg = json.loads(cuerpo)
    corte = reg["datos_hasta"]
    S = secos[(secos.clase == "seco") & (secos.fecha > corte)].copy()
    M = mayores[mayores.fecha > corte].copy()
    out = dict(huella_ok=huella == esperada, huella=huella[:16], datos_hasta=corte, hipotesis=[])

    # H0: e-valor de la mezcla de modelos sobre la última cifra (sorteos de las 2 semanas pre-registradas)
    P = {(p["loteria"], p["fecha"]): p["probabilidades"] for p in reg["predicciones"]}
    modelos = sorted({m for v in P.values() for m in v if m != "M0_uniforme"})
    logE = {m: 0.0 for m in modelos}; n0 = 0; cubiertos = set()
    for (slug, fecha), g in S.groupby(["slug", "fecha"]):
        pr = P.get((slug, fecha))
        if pr is None:
            continue
        cubiertos.add((slug, fecha))
        x = g.numero.str[-1].astype(int).values; n0 += len(x)
        for m in modelos:
            q = np.array(pr.get(m, pr["M0_uniforme"]))
            logE[m] += float(np.log(q[x] / 0.1).sum())
    E = float(np.mean([math.exp(v) for v in logE.values()])) if n0 else 1.0
    out["hipotesis"].append(dict(
        id="H0", enunciado="Ningún modelo predice la última cifra de los secos mejor que el azar.",
        regla="Se rechaza si el E de la mezcla de modelos llega a 20.", progreso=f"{len(cubiertos)} de {len(P)} sorteos",
        resultado=f"E = {_n(E, 2)} con {n0} secos", completa=len(cubiertos) >= len(P),
        veredicto="se rechaza H0: hay señal" if E >= 20 else ("H0 se sostiene" if len(cubiertos) >= len(P) else "en curso")))

    # H1: menor cuantía, cifra final 4
    S["c"] = pd.to_numeric(S.cuantia_millones, errors="coerce")
    mask = np.array([MENOR.get(s) == c for s, c in zip(S.slug, S.c)], dtype=bool)
    m = S[mask].sort_values(["fecha", "slug", "fila"]).head(400)
    k = int((m.numero.str[-1] == "4").sum()); n = len(m); p = binom_sf(k, n, 0.1) if n else None
    comp = n >= 400
    v = "en curso" if not comp else ("se sostiene" if (p < 0.01 and k / n > 0.12) else "se descarta")
    out["hipotesis"].append(dict(
        id="H1", enunciado="En los secos de menor cuantía (Medellín $10 M, Manizales $40 M, Boyacá $10 M) la última "
                           "cifra 4 sale más del 10 %.",
        regla="Binomial unilateral con los primeros 400; se sostiene si p < 0,01 y la proporción > 12 %.",
        progreso=f"{n} de 400", resultado=f"{k}/{n} = {_n(100 * k / n)} %, p = {_p(p)}" if n else "sin datos con cuantía",
        completa=comp, veredicto=v, nota="Necesita que usted suba las cuantías: LoteríaYa no las publica."))

    # H2: mayores del mismo día comparten la última cifra
    k = t = 0
    for f, g in M.sort_values(["fecha", "slug"]).groupby("fecha"):
        u = g.numero.str[-1].tolist()
        for i in range(len(u)):
            for j in range(i + 1, len(u)):
                if t < 300:
                    t += 1; k += u[i] == u[j]
    p = binom_sf(k, t, 0.1) if t else None; comp = t >= 300
    v = "en curso" if not comp else ("se sostiene" if (p < 0.01 and k / t > 0.11) else "se descarta")
    out["hipotesis"].append(dict(
        id="H2", enunciado="Los premios mayores de loterías que juegan el mismo día comparten la última cifra más del 10 %.",
        regla="Binomial unilateral con las primeras 300 parejas; se sostiene si p < 0,01 y la proporción > 11 %.",
        progreso=f"{t} de 300 parejas", resultado=f"{k}/{t} = {_n(100 * k / t)} %, p = {_p(p)}" if t else "sin datos",
        completa=comp, veredicto=v))

    # H3: terminaciones de 2 cifras compartidas entre secos del mismo día
    o = e = 0.0
    for f, g in S.groupby("fecha"):
        sets = [set(x.numero.str[-2:]) for _, x in g.groupby("slug")]
        for i in range(len(sets)):
            for j in range(i + 1, len(sets)):
                o += len(sets[i] & sets[j]); e += len(sets[i]) * len(sets[j]) / 100
    semanas = ((pd.Timestamp(S.fecha.max()) - pd.Timestamp(corte)).days / 7) if len(S) else 0
    p = poisson_sf(int(o), e) if e else None; comp = semanas >= 8
    v = "en curso" if not comp else ("se sostiene" if (p < 0.01 and o / e > 1.03) else "se descarta")
    out["hipotesis"].append(dict(
        id="H3", enunciado="Los secos de loterías del mismo día comparten terminaciones de 2 cifras más de lo esperado.",
        regla="Poisson unilateral tras 8 semanas; se sostiene si p < 0,01 y la razón > 1,03.",
        progreso=f"{_n(semanas)} de 8 semanas", resultado=f"{int(o)} observadas vs {_n(e)} esperadas (razón {_n(o / e, 3)}), p = {_p(p)}"
        if e else "sin datos", completa=comp, veredicto=v))
    return out
