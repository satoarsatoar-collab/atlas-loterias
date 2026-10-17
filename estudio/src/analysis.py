"""
PROYECTO ATLAS - Paso 2: batería de hipótesis con control de falsos descubrimientos.

Diseño (fijado ANTES de calcular cualquier estadístico):
  Secos  - exploración: 17-ago .. 26-sep-2026   | confirmación: 27-sep .. 16-oct-2026
  Mayores - exploración: ventana 17-ago .. 16-oct | confirmación: historial nov-2024 .. 16-ago-2026
  Familia primaria pre-registrada (se evalúa en confirmación pase lo que pase):
     P1 uniformidad de cada posición (secos), P2 uniformidad de las dos últimas cifras (secos),
     P3 menor cuantía vs resto (última cifra), P4 arrastre de terminaciones entre sorteos consecutivos,
     P5 coincidencias de terminaciones entre loterías el mismo día, P6 uniformidad de la cifra de unidades de la serie.
  Corrección: Holm (FWER) y Benjamini-Hochberg (FDR) sobre TODA la familia exploratoria.
  Candidatas a confirmación: q_BH < 0.10 o p < 0.01 en exploración.
"""
import json, itertools
import numpy as np
import pandas as pd
from scipy import stats
from common import *

RNG = np.random.default_rng(20261017)
may, sec = load()
SEC = sec[sec.clase == "seco"].copy()
SEC["d"] = list(digits(SEC.numero))

# S estimado por lotería (número de series emitidas): menor múltiplo de 10 > máxima serie observada
# OJO: la emisión cambia con el tiempo (p. ej. Santander tuvo series hasta 371 en 2025 y hoy no pasa de 339),
# por eso S se estima solo con datos de la ventana actual.
_mw = may[(may.fecha >= WIN_START) & may.serie.str.fullmatch(r"\d{3}", na=False)]
allser = pd.concat([SEC[["slug", "serie"]], _mw[["slug", "serie"]]])
S_HAT = allser.groupby("slug").serie.apply(lambda s: int(np.ceil((s.astype(int).max() + 1) / 10) * 10)).to_dict()
MAX_SER = allser.groupby("slug").serie.apply(lambda s: s.astype(int).max()).to_dict()


def rec(fam, tid, desc, data, res, fase, primaria=False):
    r = dict(familia=fam, id=tid, hipotesis_nula=desc, datos=data, fase=fase, primaria=primaria)
    r.update(res); return r


# ------------------------------------------------------------------------------- baterías
def number_battery(df, label, fase, fam_prefix, per_lottery=True, mc=True):
    out = []
    d = digits(df.numero); n = len(d)
    if n == 0: return out
    names = ["millares", "centenas", "decenas", "unidades"]
    for k in range(4):
        r = chisq_gof(np.bincount(d[:, k], minlength=10), np.ones(10))
        out.append(rec(fam_prefix + "A", f"{fam_prefix}A{k+1}", f"Dígito de {names[k]} uniforme", label, r, fase,
                       primaria=(fam_prefix == "S" and True)))
    out.append(rec(fam_prefix + "A", f"{fam_prefix}A5", "Frecuencia global de dígitos uniforme (4N dígitos)", label,
                   chisq_gof(np.bincount(d.ravel(), minlength=10), np.ones(10)), fase))
    if per_lottery:
        for slug, g in df.groupby("slug"):
            if len(g) < 30: continue
            dg = digits(g.numero)
            for k in range(4):
                r = chisq_gof(np.bincount(dg[:, k], minlength=10), np.ones(10), mc=((5000 if len(g) < 50 else 0) if mc else -1))
                out.append(rec(fam_prefix + "A-lot", f"{fam_prefix}A-{g.loteria.iloc[0]}-{k+1}",
                               f"{g.loteria.iloc[0]}: dígito de {names[k]} uniforme", label, r, fase))
    last2 = d[:, 2] * 10 + d[:, 3]
    out.append(rec(fam_prefix + "B", f"{fam_prefix}B1", "Dos últimas cifras uniformes (100 celdas)", label,
                   chisq_gof(np.bincount(last2, minlength=100), np.ones(100), mc=10000 if mc else -1), fase,
                   primaria=(fam_prefix == "S")))
    last3 = d[:, 1] * 100 + d[:, 2] * 10 + d[:, 3]
    if n >= 500:
        out.append(rec(fam_prefix + "B", f"{fam_prefix}B2", "Tres últimas cifras uniformes (1000 celdas)", label,
                       chisq_gof(np.bincount(last3, minlength=1000), np.ones(1000), mc=5000 if mc else -1), fase))
    first2 = d[:, 0] * 10 + d[:, 1]
    out.append(rec(fam_prefix + "B", f"{fam_prefix}B3", "Dos primeras cifras uniformes", label,
                   chisq_gof(np.bincount(first2, minlength=100), np.ones(100), mc=10000 if mc else -1), fase))
    st = structure(d); keys = list(STRUCT_P)
    out.append(rec(fam_prefix + "B", f"{fam_prefix}B4", "Estructura de repeticiones (distintos/par/dos pares/trío/cuatro) = exacta",
                   label, chisq_gof([np.sum(st == k) for k in keys], [STRUCT_P[k] for k in keys], mc=10000 if mc else -1), fase))
    pal = np.sum((d[:, 0] == d[:, 3]) & (d[:, 1] == d[:, 2]))
    out.append(rec(fam_prefix + "B", f"{fam_prefix}B5", "Palíndromos con p = 1/100", label, binom(pal, n, 0.01), fase))
    asc = np.sum(np.all(np.diff(d, axis=1) > 0, axis=1)); desc_ = np.sum(np.all(np.diff(d, axis=1) < 0, axis=1))
    out.append(rec(fam_prefix + "B", f"{fam_prefix}B6", "Dígitos estrictamente ascendentes con p = 210/10⁴", label, binom(asc, n, 0.021), fase))
    out.append(rec(fam_prefix + "B", f"{fam_prefix}B7", "Dígitos estrictamente descendentes con p = 210/10⁴", label, binom(desc_, n, 0.021), fase))
    sums = d.sum(1)
    out.append(rec(fam_prefix + "B", f"{fam_prefix}B8", "Suma de dígitos con la distribución exacta (convolución)", label,
                   chisq_gof(np.bincount(sums, minlength=37), digit_sum_pmf(), mc=10000 if mc else -1), fase))
    ev = (d % 2 == 0).sum(1)
    out.append(rec(fam_prefix + "B", f"{fam_prefix}B9", "Número de dígitos pares ~ Binomial(4, 1/2)", label,
                   chisq_gof(np.bincount(ev, minlength=5), stats.binom.pmf(range(5), 4, .5)), fase))
    dr = np.where(sums % 9 == 0, 9, sums % 9); dr[sums == 0] = 0
    pmf = digit_sum_pmf(); pr = np.zeros(10)
    for s_, p_ in enumerate(pmf): pr[0 if s_ == 0 else (9 if s_ % 9 == 0 else s_ % 9)] += p_
    out.append(rec(fam_prefix + "B", f"{fam_prefix}B10", "Raíz digital con la distribución exacta", label,
                   chisq_gof(np.bincount(dr, minlength=10), pr, mc=10000 if mc else -1), fase))
    return out


def seco_specific(df, label, fase, n_perm=2000):
    out = []
    df = df.sort_values(["slug", "fecha"])
    draws = {k: g for k, g in df.groupby(["slug", "fecha"])}
    # --- D1 arrastre de terminaciones (2 cifras) entre sorteos consecutivos de la misma lotería
    T2 = {k: g.numero.str[-2:].tolist() for k, g in draws.items()}
    T2set = {k: set(v) for k, v in T2.items()}
    lots = {}
    for (slug, f) in sorted(draws): lots.setdefault(slug, []).append((slug, f))
    def shuffle_within_lottery():
        """Reasigna al azar los números de cada lotería entre sus sorteos, conservando el tamaño de cada sorteo."""
        T, Ts = {}, {}
        for slug, keys in lots.items():
            pool = np.concatenate([T2[k] for k in keys]); RNG.shuffle(pool); i = 0
            for k in keys:
                T[k] = list(pool[i:i + len(T2[k])]); Ts[k] = set(T[k]); i += len(T2[k])
        return T, Ts
    def carry(T, Ts):
        tot = 0
        for slug, keys in lots.items():
            for a, b in zip(keys[:-1], keys[1:]):
                A = Ts[a]; tot += sum(1 for x in T[b] if x in A)
        return tot
    obs = carry(T2, T2set)
    sims = np.array([carry(*shuffle_within_lottery()) for _ in range(n_perm)]); mu = sims.mean()
    p = (1 + np.sum(np.abs(sims - mu) >= abs(obs - mu))) / (1 + n_perm)
    out.append(rec("SD", "SD1", "Las terminaciones (2 cifras) no se arrastran al sorteo siguiente de la misma lotería",
                   label, dict(stat=obs, df=np.nan, p=p, N=int(len(df)), efecto=obs / mu - 1 if mu else np.nan,
                               esperado=mu, metodo="permutación de números dentro de cada lotería"), fase, primaria=True))
    # --- D2 repeticiones exactas del número entre sorteos de la misma lotería
    o2 = 0; e2 = 0
    for slug, g in df.groupby("slug"):
        ks = g.groupby("fecha").numero.apply(list)
        for (fa, la), (fb, lb) in itertools.combinations(ks.items(), 2):
            o2 += len(set(la) & set(lb)) if True else 0
            e2 += len(la) * len(lb) / 1e4
    p2 = 2 * min(stats.poisson.cdf(o2, e2), stats.poisson.sf(o2 - 1, e2)); p2 = min(1, p2)
    out.append(rec("SD", "SD2", "Repetición exacta del número entre sorteos de la misma lotería según azar", label,
                   dict(stat=o2, df=np.nan, p=p2, N=int(len(df)), efecto=o2 / e2 - 1, esperado=e2, metodo="Poisson"), fase))
    # --- D3 autocorrelación de la suma media de dígitos por sorteo
    m = df.assign(s=digits(df.numero).sum(1)).groupby(["slug", "fecha"]).s.mean()
    def ac(series_by_lot):
        num = den = 0
        for v in series_by_lot:
            v = np.asarray(v) - 18
            num += (v[1:] * v[:-1]).sum(); den += (v ** 2).sum()
        return num / den
    by = [g.values for _, g in m.groupby(level=0)]
    o3 = ac(by); s3 = np.array([ac([RNG.permutation(v) for v in by]) for _ in range(n_perm)])
    p3 = (1 + np.sum(np.abs(s3) >= abs(o3))) / (1 + n_perm)
    out.append(rec("SD", "SD3", "Sin autocorrelación (rezago 1) en la suma media de dígitos por sorteo", label,
                   dict(stat=o3, df=np.nan, p=p3, N=len(m), efecto=o3, metodo="permutación"), fase))
    # --- D4 última cifra independiente del día de la semana
    wd = pd.to_datetime(df.fecha).dt.weekday.values; last = digits(df.numero)[:, 3]
    tab = pd.crosstab(wd, last).values
    out.append(rec("SD", "SD4", "Última cifra independiente del día de la semana", label, chisq_indep(tab), fase))
    # --- D5 colisiones de terminación dentro del mismo sorteo
    o5 = e5 = 0
    for k, g in draws.items():
        c = g.numero.str[-2:].value_counts().values; o5 += (c * (c - 1) / 2).sum(); n_ = len(g); e5 += n_ * (n_ - 1) / 2 / 100
    p5 = min(1, 2 * min(stats.poisson.cdf(o5, e5), stats.poisson.sf(o5 - 1, e5)))
    out.append(rec("SD", "SD5", "Colisiones de terminación (2 cifras) dentro de un sorteo según azar", label,
                   dict(stat=o5, df=np.nan, p=p5, N=int(len(df)), efecto=o5 / e5 - 1, esperado=e5, metodo="Poisson"), fase))
    # --- E: relaciones entre loterías del mismo día
    dates = df.groupby("fecha").slug.unique()
    def shared(T, Ts):
        tot = 0
        for f, sl in dates.items():
            if len(sl) < 2: continue
            for a, b in itertools.combinations(sl, 2): tot += len(Ts[(a, f)] & Ts[(b, f)])
        return tot
    o6 = shared(T2, T2set)
    s6 = np.array([shared(*shuffle_within_lottery()) for _ in range(n_perm)]); mu6 = s6.mean()
    p6 = (1 + np.sum(np.abs(s6 - mu6) >= abs(o6 - mu6))) / (1 + n_perm)
    out.append(rec("SE", "SE1", "Terminaciones compartidas entre loterías del mismo día según azar", label,
                   dict(stat=o6, df=np.nan, p=p6, N=int(len(df)), efecto=o6 / mu6 - 1, esperado=mu6,
                        metodo="permutación de números dentro de cada lotería (condiciona tamaños)"), fase, primaria=True))
    o7 = e7 = o8 = e8 = 0
    for f, sl in dates.items():
        for a, b in itertools.combinations(sl, 2):
            A = draws[(a, f)].numero.tolist(); B = draws[(b, f)].numero.tolist()
            o7 += len(set(A) & set(B)); e7 += len(A) * len(B) / 1e4
            rA = [x[::-1] for x in A if x != x[::-1]]
            o8 += sum(1 for x in rA if x in set(B)); e8 += len(rA) * len(B) / 1e4
    for tid, o, e, txt in [("SE2", o7, e7, "Mismo número exacto en loterías del mismo día según azar"),
                           ("SE3", o8, e8, "Número invertido en otra lotería del mismo día según azar")]:
        p_ = min(1, 2 * min(stats.poisson.cdf(o, e), stats.poisson.sf(o - 1, e)))
        out.append(rec("SE", tid, txt, label, dict(stat=o, df=np.nan, p=p_, N=int(len(df)), efecto=o / e - 1 if e else np.nan,
                                                   esperado=e, metodo="Poisson"), fase))
    mm = may.set_index(["slug", "fecha"]).numero
    o9 = e9 = 0
    for f, sl in dates.items():
        same_day = may[may.fecha == f]
        for (s2, M) in zip(same_day.slug, same_day.numero):
            for s in sl:
                if s == s2: continue
                A = draws[(s, f)].numero; o9 += (A == M).sum(); e9 += len(A) / 1e4
    p9 = min(1, 2 * min(stats.poisson.cdf(o9, e9), stats.poisson.sf(o9 - 1, e9)))
    out.append(rec("SE", "SE4", "Un seco coincide con el mayor de otra lotería del mismo día según azar", label,
                   dict(stat=o9, df=np.nan, p=p9, N=int(len(df)), efecto=o9 / e9 - 1, esperado=e9, metodo="Poisson"), fase))
    # --- F series
    units = df.serie.str[-1].astype(int).values
    out.append(rec("SF", "SF1", "Cifra de unidades de la serie uniforme (supone emisión múltiplo de 10)", label,
                   chisq_gof(np.bincount(units, minlength=10), np.ones(10)), fase, primaria=True))
    for slug, g in df.groupby("slug"):
        if len(g) < 30: continue
        S = S_HAT[slug]; v = g.serie.astype(int).values
        bins = np.minimum((v * 10) // S, 9)
        out.append(rec("SF-lot", f"SF-{g.loteria.iloc[0]}", f"{g.loteria.iloc[0]}: serie uniforme en [0,{S}) (10 tramos)", label,
                       chisq_gof(np.bincount(bins, minlength=10), np.ones(10), mc=5000 if len(g) < 50 else 0), fase))
    tab = pd.crosstab(digits(df.numero)[:, 3], units).values
    out.append(rec("SF", "SF3", "Última cifra del número independiente de la última cifra de la serie", label, chisq_indep(tab), fase))
    return out


def cuantia_battery(df, label, fase):
    """Familia C: secos de menor cuantía vs el resto (solo sorteos con cuantía de segunda fuente)."""
    out = []
    L = df[df.amount_millions.notna()].copy()
    if len(L) < 50: return out
    d = digits(L.numero); menor = L.menor_cuantia.values.astype(bool)
    for k, nm in [(3, "última cifra"), (0, "primera cifra")]:
        tab = np.vstack([np.bincount(d[menor, k], minlength=10), np.bincount(d[~menor, k], minlength=10)])
        out.append(rec("SC", f"SC-{nm}", f"Distribución de la {nm}: igual en menor cuantía y en el resto", label,
                       chisq_indep(tab), fase, primaria=(k == 3)))
    st = structure(d); keys = list(STRUCT_P)
    tab = np.vstack([[np.sum(st[menor] == k) for k in keys], [np.sum(st[~menor] == k) for k in keys]])
    out.append(rec("SC", "SC-estructura", "Estructura de repeticiones igual en menor cuantía y en el resto", label, chisq_indep(tab), fase))
    s = d.sum(1)
    mw = stats.mannwhitneyu(s[menor], s[~menor])
    out.append(rec("SC", "SC-suma", "Suma de dígitos igual en menor cuantía y en el resto", label,
                   dict(stat=mw.statistic, df=np.nan, p=mw.pvalue, N=len(s), efecto=s[menor].mean() - s[~menor].mean(),
                        metodo="Mann-Whitney"), fase))
    u = L.serie.str[-1].astype(int).values
    tab = np.vstack([np.bincount(u[menor], minlength=10), np.bincount(u[~menor], minlength=10)])
    out.append(rec("SC", "SC-serie", "Unidades de la serie igual en menor cuantía y en el resto", label, chisq_indep(tab), fase))
    out.append(rec("SC", "SC-menor-unif", "Última cifra uniforme dentro de los secos de menor cuantía", label,
                   chisq_gof(np.bincount(d[menor, 3], minlength=10), np.ones(10)), fase))
    # rango de cuantía (todas las categorías) vs última cifra, estratificado por lotería mediante permutación
    tiers = L.rango_cuantia.astype(int).values; slugs = L.slug.values
    def stat_(t):
        tot = 0
        for s_ in np.unique(slugs):
            m_ = slugs == s_
            tab = pd.crosstab(t[m_], d[m_, 3]).values
            tot += stats.chi2_contingency(tab, correction=False)[0]
        return tot
    o = stat_(tiers); sims = []
    for _ in range(1000):
        t2 = tiers.copy()
        for s_ in np.unique(slugs):
            m_ = np.where(slugs == s_)[0]; t2[m_] = RNG.permutation(t2[m_])
        sims.append(stat_(t2))
    p = (1 + np.sum(np.array(sims) >= o)) / 1001
    out.append(rec("SC", "SC-categorias", "Última cifra independiente de la categoría de cuantía (estratificado por lotería)",
                   label, dict(stat=o, df=np.nan, p=p, N=len(L), efecto=np.nan, metodo="permutación estratificada"), fase))
    return out


def mayor_specific(df, label, fase):
    out = []
    df = df.sort_values(["slug", "fecha"]); d = digits(df.numero)
    same1 = tot = same2 = 0; dist = []
    for slug, g in df.groupby("slug"):
        x = g.numero.tolist()
        for a, b in zip(x[:-1], x[1:]):
            tot += 1; same1 += a[-1] == b[-1]; same2 += a[-2:] == b[-2:]; dist.append(abs(int(a) - int(b)))
    out.append(rec("MD", "MD1", "Última cifra del mayor no se repite en el sorteo siguiente más de lo esperado (p=0,1)", label,
                   binom(same1, tot, 0.1), fase))
    out.append(rec("MD", "MD2", "Dos últimas cifras del mayor no se repiten en el sorteo siguiente (p=0,01)", label,
                   binom(same2, tot, 0.01), fase))
    dist = np.array(dist); edges = np.arange(0, 10001, 1000)
    # P(D = 0) = 1/N ; P(D = d) = 2(N-d)/N² (d >= 1), con X,Y uniformes independientes en 0..N-1
    def cdf(t):  # P(D < t)
        N = 10000
        if t <= 0: return 0.0
        return 1 / N + (2 * (t - 1) * N - (t - 1) * t) / N ** 2
    probs = np.array([cdf(b) - cdf(a) for a, b in zip(edges[:-1], edges[1:])])
    probs[-1] += 1 - probs.sum()  # incluye D = 9999 en el último tramo
    out.append(rec("MD", "MD3", "Distancia |Xₜ − Xₜ₋₁| entre mayores consecutivos sigue la ley triangular", label,
                   chisq_gof(np.histogram(dist, bins=np.arange(0, 10001, 1000))[0], probs), fase))
    # rachas: intervalos entre reapariciones de una misma última cifra.
    # La ley geométrica no sirve tal cual: en series finitas los intervalos largos quedan censurados.
    # El nulo correcto se obtiene simulando series i.i.d. de la MISMA longitud por lotería.
    def gap_hist(seqs):
        h = np.zeros(25)
        for last in seqs:
            lastpos = {}
            for i, v in enumerate(last):
                if v in lastpos: h[min(i - lastpos[v], 25) - 1] += 1
                lastpos[v] = i
        return h
    seqs = [g.numero.str[-1].astype(int).values for _, g in df.groupby("slug")]
    oh = gap_hist(seqs)
    sim_h = np.array([gap_hist([RNG.integers(0, 10, len(q)) for q in seqs]) for _ in range(2000)])
    eh = sim_h.mean(0); keep = eh > 0
    chi = lambda h: (((h - eh) ** 2)[keep] / eh[keep]).sum()
    o_md4 = chi(oh); s_md4 = np.array([chi(h) for h in sim_h])
    out.append(rec("MD", "MD4", "Intervalos entre reapariciones de una última cifra según azar (sin 'deudas'; nulo simulado)", label,
                   dict(stat=o_md4, df=np.nan, p=(1 + np.sum(s_md4 >= o_md4)) / (1 + len(s_md4)), N=int(oh.sum()),
                        efecto=np.nan, metodo="chi² vs nulo Monte Carlo"), fase))
    # versión ingenua (geométrica sin corregir) - se conserva para documentar el falso positivo
    pg = stats.geom.pmf(np.arange(1, 25), 0.1); pg = np.append(pg, 1 - pg.sum())
    out.append(rec("MD-ingenua", "MD4-ingenua", "[Prueba defectuosa a propósito] intervalos ~ Geométrica(0,1) sin corregir censura", label,
                   chisq_gof(oh, pg), fase))
    wd = pd.to_datetime(df.fecha).dt.weekday.values
    out.append(rec("MD", "MD5", "Última cifra del mayor independiente del día de la semana", label,
                   chisq_indep(pd.crosstab(wd, d[:, 3]).values), fase))
    dom = pd.to_datetime(df.fecha).dt.day.values
    out.append(rec("MD", "MD6", "Última cifra del mayor independiente de la paridad del día del mes", label,
                   chisq_indep(pd.crosstab(dom % 2, d[:, 3]).values), fase))
    # mismo día entre loterías
    k1 = k2 = n = kr = 0
    for f, g in df.groupby("fecha"):
        for a, b in itertools.combinations(g.numero.tolist(), 2):
            n += 1; k1 += a[-1] == b[-1]; k2 += a[-2:] == b[-2:]; kr += (a == b[::-1]) and a != a[::-1]
    out.append(rec("ME", "ME1", "Mayores del mismo día comparten última cifra con p=0,1", label, binom(k1, n, 0.1), fase))
    out.append(rec("ME", "ME2", "Mayores del mismo día comparten dos últimas cifras con p=0,01", label, binom(k2, n, 0.01), fase))
    ser = df[df.serie.str.fullmatch(r"\d{3}", na=False)]
    out.append(rec("MF", "MF1", "Unidades de la serie del mayor uniformes", label,
                   chisq_gof(np.bincount(ser.serie.str[-1].astype(int), minlength=10), np.ones(10)), fase))
    out.append(rec("MF", "MF2", "Última cifra del mayor independiente de la última cifra de su serie", label,
                   chisq_indep(pd.crosstab(ser.numero.str[-1], ser.serie.str[-1]).values), fase))
    return out


# ------------------------------------------------------------------------------- ejecución
if __name__ == "__main__":
    S_expl = SEC[SEC.fecha <= EXPL_END]; S_hold = SEC[SEC.fecha >= HOLD_START]
    M_win = may[may.fecha >= WIN_START]; M_hist = may[may.fecha < WIN_START]
    L_all = sec[(sec.clase == "seco") & (sec.conjunto_cuantia.fillna("") != "replicación")]
    L_expl = L_all[L_all.fecha <= EXPL_END]; L_hold = L_all[L_all.fecha >= HOLD_START]

    expl = []
    expl += number_battery(S_expl, "secos 17-ago..26-sep", "exploración", "S")
    expl += seco_specific(S_expl, "secos 17-ago..26-sep", "exploración")
    expl += cuantia_battery(L_expl, "secos con cuantía 17-ago..26-sep", "exploración")
    expl += number_battery(M_win, "mayores ventana", "exploración", "M", per_lottery=False)
    expl += mayor_specific(M_win, "mayores ventana", "exploración")
    E = pd.DataFrame(expl)
    E["p_holm"] = holm(E.p.values); E["q_bh"] = bh(E.p.values)
    E["candidata"] = (E.q_bh < 0.10) | (E.p < 0.01)

    # confirmación: mismas pruebas, datos no usados
    conf = []
    conf += number_battery(S_hold, "secos 27-sep..16-oct", "confirmación", "S")
    conf += seco_specific(S_hold, "secos 27-sep..16-oct", "confirmación")
    conf += cuantia_battery(L_hold, "secos con cuantía 27-sep..16-oct", "confirmación")
    conf += number_battery(M_hist, "mayores historial", "confirmación", "M")
    conf += mayor_specific(M_hist, "mayores historial", "confirmación")
    C = pd.DataFrame(conf)
    cand_ids = set(E[E.candidata].id); prim_ids = set(E[E.primaria].id) | set(C[C.primaria].id)
    C["evaluada_por"] = np.where(C.id.isin(cand_ids), "candidata", np.where(C.id.isin(prim_ids), "primaria", "descriptiva"))
    fam = C[C.evaluada_por != "descriptiva"].copy()
    fam["p_holm"] = holm(fam.p.values) if len(fam) else []
    fam["q_bh"] = bh(fam.p.values) if len(fam) else []
    C = C.merge(fam[["id", "datos", "p_holm", "q_bh"]], on=["id", "datos"], how="left")
    C["p_holm_todas"] = holm(C.p.values); C["q_bh_todas"] = bh(C.p.values)

    # ventana completa (descriptivo, para el informe)
    full = number_battery(SEC, "secos ventana completa", "descriptivo", "S", per_lottery=False)
    full += seco_specific(SEC, "secos ventana completa", "descriptivo")
    full += cuantia_battery(L_all, "secos con cuantía, ventana", "descriptivo")
    F = pd.DataFrame(full); F["p_holm"] = holm(F.p.values); F["q_bh"] = bh(F.p.values)

    E.to_csv(f"{OUT}/hipotesis_exploracion.csv", index=False)
    C.to_csv(f"{OUT}/hipotesis_confirmacion.csv", index=False)
    F.to_csv(f"{OUT}/hipotesis_ventana_completa.csv", index=False)
    json.dump({"S_estimado": S_HAT, "serie_max_observada": MAX_SER}, open(f"{OUT}/series_estimadas.json", "w"), indent=1)

    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 70)
    cols = ["id", "hipotesis_nula", "N", "stat", "p", "p_holm", "q_bh"]
    print("EXPLORACIÓN:", len(E), "pruebas | candidatas:", E.candidata.sum())
    print(E.sort_values("p").head(15)[cols + ["efecto"]].to_string(index=False))
    print("\nCONFIRMACIÓN (familia candidatas+primarias):")
    print(C[C.evaluada_por != "descriptiva"].sort_values("p")[cols + ["evaluada_por"]].to_string(index=False))
    print("\nVENTANA COMPLETA top:")
    print(F.sort_values("p").head(10)[cols].to_string(index=False))
