"""
PROYECTO ATLAS - Paso 4b: replicación independiente de las pistas sobre secos de menor cuantía.

Las pistas se formularon con Medellín, Manizales y Boyacá (16 sorteos con cuantía). Después se consiguieron cuantías
de 6 sorteos de la Lotería de Bogotá (bogota.gov.co y Vanguardia) que NO intervinieron en la formulación.
Pruebas fijadas ANTES de mirar los datos de Bogotá (Holm sobre las 4):
  R1  P(última cifra = 4 | seco de menor cuantía) > 0,10                      binomial unilateral
  R2  última cifra uniforme entre los secos de menor cuantía                    chi² 9 gl
  R3  misma distribución de última cifra en menor cuantía y en el resto         chi² de homogeneidad
  R4  distancia al seco más cercano del mismo sorteo igual en menor y resto     permutación dentro de cada sorteo
R4 nace de un análisis post hoc en el conjunto de formulación (se reporta allí con su valor p y su selección).
"""
import json
import numpy as np, pandas as pd
from scipy import stats
from common import *

rng = np.random.default_rng(4242)
may, sec = load()
S = sec[sec.clase == "seco"].copy(); S["n"] = S.numero.astype(int)
nums = S.groupby(["slug", "fecha"]).apply(lambda g: dict(zip(g.fila, g.n))).to_dict()


def nn_dist(r):
    o = [v for f, v in nums[(r.slug, r.fecha)].items() if f != r.fila]
    return min(min(abs(r.n - v), 10000 - abs(r.n - v)) for v in o)


def tests(L, label, B=5000):
    L = L.copy(); L["nn"] = L.apply(nn_dist, axis=1); L["lnn"] = np.log1p(L.nn)
    m = L.menor_cuantia.astype(bool).values
    u = L.numero.str[-1].astype(int).values
    out = []
    k4 = int((u[m] == 4).sum()); n = int(m.sum())
    out.append(dict(id="R1", prueba="P(cifra final 4 | menor cuantía) > 0,10", n=n, observado=f"{k4}/{n} = {100*k4/n:.1f} %",
                    p=stats.binomtest(k4, n, 0.1, alternative="greater").pvalue))
    r = chisq_gof(np.bincount(u[m], minlength=10), np.ones(10))
    out.append(dict(id="R2", prueba="Última cifra uniforme en menor cuantía", n=n, observado=f"chi² = {r['stat']:.1f}", p=r["p"]))
    r = chisq_indep(np.vstack([np.bincount(u[m], minlength=10), np.bincount(u[~m], minlength=10)]))
    out.append(dict(id="R3", prueba="Última cifra igual en menor cuantía y resto", n=len(L), observado=f"V = {r['efecto']:.2f}", p=r["p"]))
    g = L.groupby(["slug", "fecha"]).indices
    stat = lambda mm: L.lnn.values[mm].mean() - L.lnn.values[~mm].mean()
    o = stat(m); sims = []
    for _ in range(B):
        mm = m.copy()
        for idx in g.values(): mm[idx] = rng.permutation(mm[idx])
        sims.append(stat(mm))
    sims = np.array(sims)
    med = L.groupby("menor_cuantia").nn.median()
    out.append(dict(id="R4", prueba="Distancia al seco más cercano igual en menor y resto", n=len(L),
                    observado=f"mediana {med.get(True):.0f} vs {med.get(False):.0f} (dif. log {o:+.2f})",
                    p=(1 + np.sum(np.abs(sims) >= abs(o))) / (1 + B)))
    R = pd.DataFrame(out); R.insert(0, "conjunto", label); R["p_holm"] = holm(R.p.values)
    return R


if __name__ == "__main__":
    F = S[S.conjunto_cuantia.fillna("") == "formulación"]
    Rp = S[S.conjunto_cuantia.fillna("") == "replicación"]
    res = pd.concat([tests(F, "formulación (Medellín, Manizales, Boyacá; post hoc)"),
                     tests(Rp, "replicación independiente (Bogotá, 6 sorteos)")])
    res.to_csv(f"{OUT}/replicacion_menor_cuantia.csv", index=False)
    cc = pd.read_csv(f"{ROOT}/data/processed/label_crosscheck.csv")
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60)
    print(res.to_string(index=False))
    print(cc[cc.loteria == "Bogotá"].to_string(index=False))
