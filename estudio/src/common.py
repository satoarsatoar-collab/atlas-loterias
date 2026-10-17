"""Utilidades compartidas: carga de datos, aritmética de dígitos, pruebas y correcciones."""
import os
import numpy as np
import pandas as pd
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
OUT = os.path.join(ROOT, "out")
os.makedirs(OUT, exist_ok=True)

EXPL_END = "2026-09-26"      # secos: fase exploratoria 17-ago .. 26-sep
HOLD_START = "2026-09-27"    # secos: fase confirmatoria 27-sep .. 16-oct (no se mira antes)
WIN_START = "2026-08-17"


def load():
    may = pd.read_csv(os.path.join(PROC, "mayores.csv"), dtype={"numero": str, "serie": str, "sorteo": str})
    sec = pd.read_csv(os.path.join(PROC, "secos.csv"), dtype={"numero": str, "serie": str, "mayor": str,
                                                               "serie_mayor": str, "sorteo": str})
    may = may[may.numero.str.fullmatch(r"\d{4}", na=False)].copy()
    return may, sec


def digits(nums):
    """Matriz N x 4 de dígitos a partir de cadenas de 4 caracteres."""
    a = np.array([[int(c) for c in n] for n in nums], dtype=int)
    return a.reshape(-1, 4)


# --- probabilidades exactas bajo el modelo nulo (4 dígitos i.i.d. uniformes) -----------------
STRUCT_P = {"todos_distintos": 5040 / 1e4, "un_par": 4320 / 1e4, "dos_pares": 270 / 1e4,
            "trio": 360 / 1e4, "cuatro_iguales": 10 / 1e4}


def structure(d):
    out = []
    for row in d:
        c = sorted(np.bincount(row, minlength=10)[np.bincount(row, minlength=10) > 0], reverse=True)
        out.append({(1, 1, 1, 1): "todos_distintos", (2, 1, 1): "un_par", (2, 2): "dos_pares",
                    (3, 1): "trio", (4,): "cuatro_iguales"}[tuple(c)])
    return np.array(out)


def digit_sum_pmf():
    p = np.ones(10) / 10
    pmf = p
    for _ in range(3):
        pmf = np.convolve(pmf, p)
    return pmf  # soporte 0..36


# --- pruebas -----------------------------------------------------------------------------------
def chisq_gof(obs, p_exp, mc=0, rng=None):
    """Chi-cuadrado de bondad de ajuste. Si hay celdas con esperado < 5, p por Monte Carlo."""
    obs = np.asarray(obs, float); p_exp = np.asarray(p_exp, float); p_exp = p_exp / p_exp.sum()
    n = obs.sum(); exp = n * p_exp
    stat = ((obs - exp) ** 2 / exp).sum()
    df = len(obs) - 1
    if mc == -1:  # modo rápido (simulaciones): siempre asintótico
        p = stats.chi2.sf(stat, df); method = "chi² GOF (asintótico)"
    elif mc or exp.min() < 5:
        rng = rng or np.random.default_rng(12345)
        sims = rng.multinomial(int(n), p_exp, size=mc or 20000)
        sstat = ((sims - exp) ** 2 / exp).sum(1)
        p = (1 + (sstat >= stat - 1e-12).sum()) / (1 + len(sstat))
        method = "chi² (p Monte Carlo)"
    else:
        p = stats.chi2.sf(stat, df); method = "chi² GOF"
    w = np.sqrt(stat / n) if n else np.nan
    return dict(stat=stat, df=df, p=p, N=int(n), efecto=w, metodo=method)


def chisq_indep(table):
    table = np.asarray(table, float)
    table = table[table.sum(1) > 0][:, table.sum(0) > 0]
    chi2, p, df, exp = stats.chi2_contingency(table, correction=False)
    n = table.sum(); k = min(table.shape) - 1
    v = np.sqrt(chi2 / (n * k)) if k > 0 else np.nan
    return dict(stat=chi2, df=df, p=p, N=int(n), efecto=v, metodo="chi² independencia (V de Cramér)")


def binom(k, n, p0):
    r = stats.binomtest(int(k), int(n), p0)
    ci = r.proportion_ci(0.95, method="wilson")
    return dict(stat=k / n if n else np.nan, df=np.nan, p=r.pvalue, N=int(n),
                efecto=(k / n - p0) if n else np.nan, ci_lo=ci.low, ci_hi=ci.high, metodo="binomial exacta")


def mde_w(n, df, alpha=0.05, power=0.80):
    """Tamaño de efecto w de Cohen mínimo detectable con potencia dada."""
    crit = stats.chi2.ppf(1 - alpha, df)
    lo, hi = 1e-6, 5.0
    for _ in range(80):
        mid = (lo + hi) / 2
        pw = stats.ncx2.sf(crit, df, n * mid ** 2)
        lo, hi = (lo, mid) if pw >= power else (mid, hi)
    return hi


def holm(p):
    p = np.asarray(p, float); m = len(p); o = np.argsort(p)
    adj = np.empty(m); run = 0
    for i, idx in enumerate(o):
        run = max(run, (m - i) * p[idx]); adj[idx] = min(1, run)
    return adj


def bh(p):
    p = np.asarray(p, float); m = len(p); o = np.argsort(p)[::-1]
    adj = np.empty(m); run = 1
    for i, idx in enumerate(o):
        rank = m - i
        run = min(run, p[idx] * m / rank); adj[idx] = run
    return adj


def wilson(k, n, z=1.96):
    if n == 0: return (np.nan, np.nan)
    ph = k / n; den = 1 + z ** 2 / n
    c = (ph + z ** 2 / (2 * n)) / den; h = z * np.sqrt(ph * (1 - ph) / n + z ** 2 / (4 * n ** 2)) / den
    return c - h, c + h
