"""
PROYECTO ATLAS - Paso 4: modelos predictivos y validación temporal (walk-forward).

Objetivo de predicción: la última cifra (10 clases) y las dos últimas cifras (100 clases),
  (a) del premio mayor de cada lotería, nov-2024 .. oct-2026
  (b) de cada seco independiente, 17-ago .. 16-oct-2026
Regla: para predecir un sorteo de fecha t solo se usan sorteos con fecha < t.
Los hiperparámetros se fijaron a priori (no se ajustan con los datos):
  Dirichlet alfa=20 por celda, jerárquico kappa=50, ventana 'caliente/fría' = 20 mayores o 3 sorteos de secos,
  regresión logística L2 con C=0,1 reentrenada cada 100 predicciones.
Holdout final que no interviene en nada: mayores 17-ago..16-oct-2026; secos 27-sep..16-oct-2026.
"""
import json, warnings
import numpy as np, pandas as pd
from common import *
from sklearn.linear_model import LogisticRegression

warnings.filterwarnings("ignore")
RNG = np.random.default_rng(99)
may, sec = load()
LN10 = np.log(10)


def dist_counts(c, a=1.0):
    c = np.asarray(c, float) + a; return c / c.sum()


def predictors_mayores(df, K=10, kind="last"):
    """Devuelve dict modelo -> matriz (n, K) de probabilidades, y el vector y."""
    df = df.sort_values(["fecha", "slug"]).reset_index(drop=True)
    y = df.numero.str[-1].astype(int).values if kind == "last" else df.numero.str[-2:].astype(int).values
    n = len(df); P = {m: np.zeros((n, K)) for m in ["M0_uniforme", "M1_frec_loteria", "M2_frec_global",
                                                     "M3_dirichlet20", "M4_jerarquico", "M5_caliente", "M6_fria",
                                                     "M7_markov", "M8_logistica"]}
    lots = df.slug.values; dates = df.fecha.values
    prev_digits = {}  # slug -> dígitos del mayor anterior
    feats, X_rows = [], []
    slugs = sorted(df.slug.unique()); sidx = {s: i for i, s in enumerate(slugs)}
    def feat(i):
        v = np.zeros(40 + len(slugs) + 7)
        pd_ = prev_digits.get(lots[i])
        if pd_ is not None:
            for k, dgt in enumerate(pd_): v[k * 10 + dgt] = 1
        v[40 + sidx[lots[i]]] = 1; v[40 + len(slugs) + pd.Timestamp(dates[i]).weekday()] = 1
        return v
    hist_by_lot = {s: [] for s in slugs}
    trans = np.zeros((K, K)) if K == 10 else None
    clf = None; last_fit = -999; Xtr, ytr = [], []
    i = 0
    while i < n:
        j = i
        while j < n and dates[j] == dates[i]: j += 1          # todos los sorteos de la misma fecha
        all_past = np.concatenate([np.array(v, int) for v in hist_by_lot.values()]) if any(hist_by_lot.values()) else np.array([], int)
        gc = np.bincount(all_past, minlength=K)
        pg = dist_counts(gc)
        if K == 10 and len(Xtr) >= 200 and (len(Xtr) - last_fit >= 100):
            clf = LogisticRegression(C=0.1, max_iter=2000).fit(np.array(Xtr), np.array(ytr)); last_fit = len(Xtr)
        for t in range(i, j):
            h = np.array(hist_by_lot[lots[t]], int); lc = np.bincount(h, minlength=K)
            P["M0_uniforme"][t] = 1 / K
            P["M1_frec_loteria"][t] = dist_counts(lc)
            P["M2_frec_global"][t] = pg
            P["M3_dirichlet20"][t] = dist_counts(lc, 20.0)
            P["M4_jerarquico"][t] = (lc + 50 * pg) / (lc.sum() + 50)
            hc = np.bincount(h[-20:], minlength=K)
            P["M5_caliente"][t] = dist_counts(hc)
            cold = (hc.max() + 1 - hc).astype(float); P["M6_fria"][t] = cold / cold.sum()
            if K == 10 and len(h):
                row = trans[h[-1]] + 1; P["M7_markov"][t] = row / row.sum()
            else:
                P["M7_markov"][t] = 1 / K
            if K == 10 and clf is not None:
                pr = np.full(K, 1e-9); pr[clf.classes_] = clf.predict_proba(feat(t)[None])[0]; P["M8_logistica"][t] = pr / pr.sum()
            else:
                P["M8_logistica"][t] = 1 / K
        for t in range(i, j):                                   # se revela el resultado
            if K == 10:
                Xtr.append(feat(t)); ytr.append(y[t])
                h = hist_by_lot[lots[t]]
                if h: trans[h[-1], y[t]] += 1
            hist_by_lot[lots[t]].append(y[t])
            prev_digits[lots[t]] = [int(c) for c in df.numero.iloc[t]]
        i = j
    if K != 10:
        for m in ["M7_markov", "M8_logistica"]: P.pop(m)
    return df, y, P


def predictors_secos(df, K=10):
    df = df.sort_values(["fecha", "slug", "fila"]).reset_index(drop=True)
    y = (df.numero.str[-1] if K == 10 else df.numero.str[-2:]).astype(int).values
    keys = list(zip(df.slug, df.fecha)); n = len(df)
    names = ["M0_uniforme", "M1_frec_loteria", "M2_frec_global", "M3_dirichlet20", "M4_jerarquico", "M5_caliente", "M6_fria"]
    if K == 10: names.append("M7_cond_mayor_previo")
    P = {m: np.zeros((n, K)) for m in names}
    past_lot = {}; past_all = []; draws_lot = {}
    prev_mayor = {}; cond = np.zeros((10, 10))
    mm = may.set_index(["slug", "fecha"]).numero.to_dict()
    for f in sorted(df.fecha.unique()):
        idx = np.where(df.fecha.values == f)[0]
        gc = np.bincount(np.array(past_all, int), minlength=K); pg = dist_counts(gc)
        for t in idx:
            s = df.slug.iloc[t]
            lc = np.bincount(np.array(past_lot.get(s, []), int), minlength=K)
            recent = sum(draws_lot.get(s, [])[-3:], []); hc = np.bincount(np.array(recent, int), minlength=K)
            P["M0_uniforme"][t] = 1 / K
            P["M1_frec_loteria"][t] = dist_counts(lc)
            P["M2_frec_global"][t] = pg
            P["M3_dirichlet20"][t] = dist_counts(lc, 20.0)
            P["M4_jerarquico"][t] = (lc + 50 * pg) / (lc.sum() + 50)
            P["M5_caliente"][t] = dist_counts(hc)
            cold = (hc.max() + 1 - hc).astype(float); P["M6_fria"][t] = cold / cold.sum()
            if K == 10:
                pm = prev_mayor.get(s)
                P["M7_cond_mayor_previo"][t] = dist_counts(cond[pm]) if pm is not None else 1 / K
        for s, g in df.iloc[idx].groupby("slug"):
            vals = y[g.index].tolist()
            past_lot.setdefault(s, []).extend(vals); past_all.extend(vals); draws_lot.setdefault(s, []).append(vals)
            if K == 10:
                pm = prev_mayor.get(s)
                if pm is not None:
                    for v in vals: cond[pm, v] += 1
                prev_mayor[s] = int(mm.get((s, f), "0000")[-1])
    return df, y, P


def evaluate(y, P, groups, mask, K):
    """Log-loss, Brier, acierto top-1 y calibración; IC por bootstrap de conglomerados (sorteos)."""
    res = []
    ug = np.unique(groups[mask]); gidx = {g: np.where((groups == g) & mask)[0] for g in ug}
    B = 1000; boots = [RNG.choice(ug, len(ug)) for _ in range(B)]
    base_ll = np.full(len(y), np.log(K))
    for m, pr in P.items():
        p_true = np.clip(pr[np.arange(len(y)), y], 1e-12, 1)
        ll = -np.log(p_true); diff = ll - base_ll
        onehot = np.zeros_like(pr); onehot[np.arange(len(y)), y] = 1
        brier = ((pr - onehot) ** 2).sum(1)
        top = pr.argmax(1) == y
        # si el modelo empata en todo (uniforme) el 'top-1' es aleatorio: acierto esperado 1/K
        flat = np.isclose(pr.max(1), pr.min(1))
        top = np.where(flat, RNG.random(len(y)) < 1 / K, top)
        msk = mask
        d_mean = diff[msk].mean()
        bs = np.array([np.mean(np.concatenate([diff[gidx[g]] for g in b])) for b in boots])
        hits = top[msk].sum(); nn = msk.sum()
        # calibración: ECE sobre todas las probabilidades de clase
        pp = pr[msk].ravel(); oo = onehot[msk].ravel(); bins = np.quantile(pp, np.linspace(0, 1, 11)); bins[-1] += 1e-9
        ece = 0
        for a, b in zip(bins[:-1], bins[1:]):
            sel = (pp >= a) & (pp < b)
            if sel.any(): ece += sel.mean() * abs(pp[sel].mean() - oo[sel].mean())
        res.append(dict(modelo=m, n=int(nn), logloss=ll[msk].mean(), delta_vs_uniforme=d_mean,
                        delta_ic95_lo=np.quantile(bs, 0.025), delta_ic95_hi=np.quantile(bs, 0.975),
                        habilidad_pct=-100 * d_mean / np.log(K), brier=brier[msk].mean(),
                        brier_uniforme=(1 - 1 / K), acierto_top1=hits / nn, acierto_ic_lo=wilson(hits, nn)[0],
                        acierto_ic_hi=wilson(hits, nn)[1], base_azar=1 / K, ece=ece))
    return pd.DataFrame(res)


if __name__ == "__main__":
    out = {}
    tables = []
    # ---------------- (a) mayores
    for K, kind in [(10, "last"), (100, "last2")]:
        df, y, P = predictors_mayores(may, K, kind)
        groups = (df.slug + "_" + df.fecha).values
        warm = df.groupby("slug").cumcount().values >= 10     # se excluyen los 10 primeros de cada lotería
        for per, msk in [("desarrollo (nov-2024..16-ago-2026)", (df.fecha < WIN_START).values & warm),
                         ("holdout final (17-ago..16-oct-2026)", (df.fecha >= WIN_START).values)]:
            r = evaluate(y, P, groups, msk, K); r.insert(0, "periodo", per); r.insert(0, "objetivo", f"mayor: {'última cifra' if K==10 else 'dos últimas'}")
            tables.append(r)
    # ---------------- (b) secos
    S = sec[sec.clase == "seco"].copy()
    for K in (10, 100):
        df, y, P = predictors_secos(S, K)
        groups = (df.slug + "_" + df.fecha).values
        first = df.fecha.values >= "2026-08-24"   # una semana de arranque para tener historia
        for per, msk in [("desarrollo (24-ago..26-sep)", first & (df.fecha.values <= EXPL_END)),
                         ("holdout final (27-sep..16-oct)", df.fecha.values >= HOLD_START)]:
            r = evaluate(y, P, groups, msk, K); r.insert(0, "periodo", per); r.insert(0, "objetivo", f"seco: {'última cifra' if K==10 else 'dos últimas'}")
            tables.append(r)
    T = pd.concat(tables)
    T.to_csv(f"{OUT}/validacion_modelos.csv", index=False)
    pd.set_option("display.width", 250)
    print(T[["objetivo", "periodo", "modelo", "n", "delta_vs_uniforme", "delta_ic95_lo", "delta_ic95_hi", "habilidad_pct", "acierto_top1", "ece"]]
          .round(4).to_string(index=False))
