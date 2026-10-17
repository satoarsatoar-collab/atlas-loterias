"""
PROYECTO ATLAS - Paso 3: ¿qué tan "extraordinario" es el patrón más llamativo si TODO es azar?

Se generan loterías sintéticas perfectamente uniformes con la misma estructura que los datos reales
(mismas loterías, mismos sorteos, mismo número de secos por sorteo) y se les aplica la misma batería
exploratoria. Así se mide el sesgo de selección: cuántas pruebas salen 'significativas' por puro azar
y qué tan pequeño es el menor valor p.
También se cuantifica el patrón post hoc de la cifra 4 en los secos de menor cuantía.
"""
import json
import numpy as np, pandas as pd
from common import *
import analysis as A
from scipy import stats
binom_test_p = lambda k, n: stats.binomtest(k, n, 0.1).pvalue

rng = np.random.default_rng(7)
S_expl = A.SEC[A.SEC.fecha <= EXPL_END].copy()
R = 300
minp, n05, nbh = [], [], []
for r in range(R):
    fake = S_expl.copy()
    fake["numero"] = [f"{x:04d}" for x in rng.integers(0, 10000, len(fake))]
    res = pd.DataFrame(A.number_battery(fake, "nulo", "sim", "S", per_lottery=True, mc=False))
    p = res.p.values
    minp.append(p.min()); n05.append((p < 0.05).sum()); nbh.append((bh(p) < 0.10).sum())
real = pd.DataFrame(A.number_battery(S_expl, "real", "real", "S", per_lottery=True, mc=False))
out = dict(
    replicas=R, pruebas_por_replica=int(len(real)),
    nulo_mediana_min_p=float(np.median(minp)), nulo_p05_min_p=float(np.quantile(minp, 0.05)),
    nulo_media_p_menor_005=float(np.mean(n05)), nulo_p95_p_menor_005=float(np.quantile(n05, 0.95)),
    nulo_frac_replicas_con_descubrimiento_BH=float(np.mean(np.array(nbh) > 0)),
    real_min_p=float(real.p.min()), real_p_menor_005=int((real.p < 0.05).sum()),
    real_descubrimientos_BH=int((bh(real.p.values) < 0.10).sum()),
    percentil_real_min_p_en_nulo=float(np.mean(np.array(minp) <= real.p.min())),
)
# ---- patrón post hoc: cifra final 4 en secos de menor cuantía
L = A.sec[(A.sec.clase == "seco") & A.sec.menor_cuantia.fillna(False).astype(bool) & (A.sec.conjunto_cuantia.fillna("") == "formulación")]
u = L.numero.str[-1].astype(int).values; n = len(u); c = np.bincount(u, minlength=10)
sims = rng.multinomial(n, np.ones(10) / 10, size=200000).max(1)
out["menor_cuantia"] = dict(
    n=int(n), conteos=c.tolist(), cifra_4=int(c[4]), prop_4=float(c[4] / n), ic95_4=list(wilson(c[4], n)),
    p_binomial_sin_ajustar=float(binom_test_p(int(c[4]), n)),
    p_ajustada_por_eleccion_de_cifra=float(np.mean(sims >= c.max())),
)
json.dump(out, open(f"{OUT}/simulacion_nulo.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
