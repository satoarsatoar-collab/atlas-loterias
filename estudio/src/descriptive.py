"""
PROYECTO ATLAS - Tablas descriptivas: frecuencias por posición con IC simultáneos, potencia y efectos mínimos detectables.
"""
import json
import numpy as np, pandas as pd
from scipy import stats
from common import *

may, sec = load()
S = sec[sec.clase == "seco"]
Mh = may[may.fecha < WIN_START]
z_sim = stats.norm.ppf(1 - 0.05 / (2 * 40))   # Bonferroni: 40 celdas (10 dígitos x 4 posiciones)

def freq_table(df, label):
    d = digits(df.numero); n = len(d); rows = []
    for k, pos in enumerate(["millares", "centenas", "decenas", "unidades"]):
        c = np.bincount(d[:, k], minlength=10)
        for dig in range(10):
            lo, hi = wilson(c[dig], n, z_sim)
            rows.append(dict(conjunto=label, posicion=pos, digito=dig, conteo=int(c[dig]), pct=100 * c[dig] / n,
                             ic_simultaneo_lo=100 * lo, ic_simultaneo_hi=100 * hi, esperado_pct=10.0))
    return pd.DataFrame(rows)

T = pd.concat([freq_table(S, "secos 17-ago..16-oct"), freq_table(Mh, "mayores nov-2024..16-ago-2026")])
T.to_csv(f"{OUT}/frecuencias_posicion.csv", index=False)

# potencia: efecto mínimo detectable (w de Cohen) y su traducción a 'una cifra con probabilidad 10% + delta'
sets = {"secos exploración": (S.fecha <= EXPL_END).sum(), "secos confirmación": (S.fecha >= HOLD_START).sum(),
        "secos ventana completa": len(S), "secos de menor cuantía (con fuente de cuantía)": int((S.menor_cuantia.fillna(False).astype(bool) & (S.conjunto_cuantia.fillna("") == "formulación")).sum()),
        "secos con cuantía (todas las categorías)": int((S.conjunto_cuantia.fillna("") == "formulación").sum()),
        "un seco típico por lotería (ventana)": int(S.groupby("slug").size().median()),
        "mayores historial (todas)": len(Mh), "mayores de una lotería (historial)": int(Mh.groupby("slug").size().median())}
P = []
for k, n in sets.items():
    w = mde_w(n, 9); w100 = mde_w(n, 99)
    P.append(dict(conjunto=k, N=int(n), w_min_10_celdas=w, delta_pp_una_cifra=100 * 0.3 * w,
                  w_min_100_celdas=w100, N_para_detectar_11pct=int(np.ceil((stats.ncx2.ppf(0.2, 9, 0) * 0 + 1) * 0)) or None))
P = pd.DataFrame(P)
# N necesario para detectar una cifra con 11% (en lugar de 10%) con 80% de potencia: w = delta/0.3
w_target = 0.01 / 0.3
crit = stats.chi2.ppf(0.95, 9)
lo, hi = 10, 10_000_000
while hi - lo > 1:
    mid = (lo + hi) // 2
    lo, hi = (lo, mid) if stats.ncx2.sf(crit, 9, mid * w_target ** 2) >= 0.8 else (mid, hi)
P["N_para_detectar_11pct"] = hi
P.to_csv(f"{OUT}/potencia.csv", index=False)

# resumen de frecuencias extremas
summ = {}
for lab, g in T.groupby("conjunto"):
    g = g.assign(desv=g.pct - 10)
    i = g.desv.abs().idxmax()
    summ[lab] = dict(max_desviacion_pp=float(g.loc[i, "desv"]), posicion=g.loc[i, "posicion"], digito=int(g.loc[i, "digito"]),
                     celdas_fuera_ic_simultaneo=int(((g.ic_simultaneo_lo > 10) | (g.ic_simultaneo_hi < 10)).sum()))
json.dump(summ, open(f"{OUT}/frecuencias_resumen.json", "w"), ensure_ascii=False, indent=1)
print(P.round(4).to_string(index=False)); print(json.dumps(summ, ensure_ascii=False, indent=1))
print(T[T.conjunto.str.startswith("secos")].pivot(index="digito", columns="posicion", values="pct").round(2))
