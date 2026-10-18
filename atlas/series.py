"""Análisis descriptivo de las series de los secos, por lotería: ¿salen todas por igual?

Bajo el azar, la serie de cada seco independiente es uniforme entre 001 y S-1 (la 000 se excluye en la auditoría).
Tres pruebas por lotería, con valores p por simulación (exactos para estas cantidades de datos):
  franjas       ¿caen más series en alguna décima parte del rango?            chi² sobre 10 franjas
  última cifra  ¿alguna terminación de serie sale más?                        chi² sobre 10 cifras
  repetición    ¿la serie más repetida sale más veces de lo normal?           máximo de un multinomial
Con 14 loterías x 3 pruebas se corrige por comparaciones múltiples (Holm).
"""
from __future__ import annotations

import numpy as np

from .config import NOMBRE


def _holm(p):
    p = np.asarray(p, float); m = len(p); o = np.argsort(p); adj = np.empty(m); run = 0.0
    for i, k in enumerate(o):
        run = max(run, (m - i) * p[k]); adj[k] = min(1.0, run)
    return adj


def _chi_mc(obs, p0, rng, B=4000):
    n = int(obs.sum()); exp = n * p0; ok = exp > 0
    stat = float((((obs - exp) ** 2)[ok] / exp[ok]).sum())
    sims = rng.multinomial(n, p0, size=B)
    s = (((sims - exp) ** 2)[:, ok] / exp[ok]).sum(1)
    return stat, float((1 + (s >= stat - 1e-9).sum()) / (1 + B))


def analizar(M, minimo=60, seed=2026) -> dict:
    rng = np.random.default_rng(seed)
    filas, pvals = [], []
    for slug in M.lots:
        vals = [d["sr"]["serie"] for d in M.draws["seco"] if d["slug"] == slug]
        vals = np.concatenate(vals) if vals else np.zeros(0, int)
        S = M.S[slug]; sop = M.soporte("seco", slug); m = int(sop.sum()); n = int(len(vals))
        fila = dict(slug=slug, loteria=NOMBRE.get(slug, slug), series_en_juego=S, rango=f"001–{S - 1:03d}", secos=n)
        if n < minimo:
            fila.update(estado="pocos datos"); filas.append(fila); continue
        cuenta = np.bincount(vals, minlength=S)
        _, p_fr = _chi_mc(np.bincount(vals * 10 // S, minlength=10).astype(float), M.info("serie_franja", "seco", slug)[1], rng)
        _, p_u = _chi_mc(np.bincount(vals % 10, minlength=10).astype(float), M.info("serie_u", "seco", slug)[1], rng)
        sims_max = rng.multinomial(n, sop / m, size=3000).max(1)
        mx = int(cuenta.max())
        p_max = float((1 + (sims_max >= mx).sum()) / (1 + len(sims_max)))
        lo, hi = (int(x) for x in np.percentile(sims_max, [5, 95]))
        top = np.argsort(-cuenta, kind="stable")[:5]
        fila.update(estado="ok", esperado_por_serie=round(n / m, 2), mas_repetidas=[[f"{i:03d}", int(cuenta[i])] for i in top],
                    max_veces=mx, max_normal=f"{lo}–{hi}" if lo != hi else str(lo), p_franjas=p_fr, p_ultima=p_u, p_repeticion=p_max,
                    nunca_salieron=int((cuenta[sop] == 0).sum()))
        filas.append(fila); pvals += [p_fr, p_u, p_max]
    adj = list(_holm(pvals)) if pvals else []
    for f in filas:
        if f.get("estado") == "ok":
            f["p_holm_min"] = float(min(adj.pop(0), adj.pop(0), adj.pop(0)))
            f["veredicto"] = "desigual: revisar" if f["p_holm_min"] < 0.05 else "pareja, como el azar"
    return dict(loterias=filas, pruebas=len(pvals),
                desiguales=[f["loteria"] for f in filas if f.get("veredicto", "").startswith("desigual")])
