"""
PROYECTO ATLAS - Paso 5: ¿puede generar dinero? Valor esperado exacto por enumeración de TODOS los billetes.

Para cada sorteo simulado (mayor, serie del mayor y secos al azar) se calcula el premio que recibiría cada uno de los
10.000 x S billetes según el plan de premios (premios no acumulables: cada billete cobra el mayor premio al que tiene
derecho; se reporta también la cota con premios acumulables). El valor esperado de un billete es el promedio.

Fuentes del plan: LoteríaYa (páginas de Lotería de Medellín y Lotería de Bogotá, consultadas el 17-oct-2026).
Impuestos: premios > 48 UVT (UVT 2026 = $52.374) pagan 17 % (impuesto a ganadores, Ley 643 de 2001) y luego 20 %
de retención por ganancia ocasional sobre el remanente (arts. 306, 317 y 402 E.T.) -> neto = 66,4 % del premio.
Supuesto clave: S (número de series emitidas) se estima con la serie máxima observada (no hay dato oficial a mano).
"""
import json
import numpy as np, pandas as pd
from common import *

UVT = 52374; UMBRAL = 48 * UVT
rng = np.random.default_rng(2026)
NUMS = np.array([[int(c) for c in f"{i:04d}"] for i in range(10000)])


def net(v):
    v = np.asarray(v, float); return np.where(v > UMBRAL, v * 0.83 * 0.80, v)


def plan_medellin():
    secos = [1000e6] * 2 + [700e6] * 2 + [500e6] * 2 + [100e6] * 6 + [50e6] * 7 + [20e6] * 10 + [10e6] * 15
    same = [  # (nombre, valor, predicado sobre (dígitos del billete D, dígitos del mayor m)) con la serie del mayor
        ("tres primeras con serie", 36e6, lambda D, m: np.all(D[:, :3] == m[:3], 1)),
        ("tres últimas con serie", 36e6, lambda D, m: np.all(D[:, 1:] == m[1:], 1)),
        ("dos últimas con serie", 6e6, lambda D, m: np.all(D[:, 2:] == m[2:], 1)),
        ("dos primeras con serie", 6e6, lambda D, m: np.all(D[:, :2] == m[:2], 1)),
        ("última cifra con serie", 364591, lambda D, m: D[:, 3] == m[3]),
        ("serie del mayor", 25301, lambda D, m: np.ones(len(D), bool)),
    ]
    diff = [  # en serie distinta a la del mayor
        ("mayor en diferente serie", 5e6, lambda D, m: np.all(D == m, 1)),
        ("tres primeras diferente serie", 54217, lambda D, m: np.all(D[:, :3] == m[:3], 1)),
        ("tres últimas diferente serie", 54217, lambda D, m: np.all(D[:, 1:] == m[1:], 1)),
        ("dos últimas diferente serie", 36145, lambda D, m: np.all(D[:, 2:] == m[2:], 1)),
        ("dos primeras diferente serie", 36145, lambda D, m: np.all(D[:, :2] == m[:2], 1)),
        ("última diferente serie", 25301, lambda D, m: D[:, 3] == m[3]),
    ]
    return dict(nombre="Lotería de Medellín", mayor=16000e6, secos=secos, seco_dif_serie=36145,
                same=same, diff=diff, billete=21000, fracciones=2, S_obs_max=497)


def plan_bogota():
    secos = [1000e6] + [500e6] + [200e6] * 3 + [50e6] * 6 + [20e6] * 12 + [10e6] * 30
    perm = lambda D, m: (np.sort(D, 1) == np.sort(m)).all(1) & ~np.all(D == m, 1)
    same = [
        ("dos primeras y última con serie", 14e6, lambda D, m: np.all(D[:, :2] == m[:2], 1) & (D[:, 3] == m[3])),
        ("primera y dos últimas con serie", 14e6, lambda D, m: (D[:, 0] == m[0]) & np.all(D[:, 2:] == m[2:], 1)),
        ("tres últimas con serie", 14e6, lambda D, m: np.all(D[:, 1:] == m[1:], 1)),
        ("tres primeras con serie", 14e6, lambda D, m: np.all(D[:, :3] == m[:3], 1)),
        ("dos primeras con serie", 2e6, lambda D, m: np.all(D[:, :2] == m[:2], 1)),
        ("dos últimas con serie", 2e6, lambda D, m: np.all(D[:, 2:] == m[2:], 1)),
        ("primera y última con serie", 2e6, lambda D, m: (D[:, 0] == m[0]) & (D[:, 3] == m[3])),
        ("mayor en cualquier orden con serie", 2e6, perm),
        ("última con serie", 65060, lambda D, m: D[:, 3] == m[3]),
        ("serie del mayor", 21686, lambda D, m: np.ones(len(D), bool)),
    ]
    diff = [
        ("mayor en diferente serie", 6e6, lambda D, m: np.all(D == m, 1)),
        ("tres primeras dif. serie", 65060, lambda D, m: np.all(D[:, :3] == m[:3], 1)),
        ("primera y dos últimas dif. serie", 65060, lambda D, m: (D[:, 0] == m[0]) & np.all(D[:, 2:] == m[2:], 1)),
        ("tres últimas dif. serie", 65060, lambda D, m: np.all(D[:, 1:] == m[1:], 1)),
        ("dos primeras y última dif. serie", 65060, lambda D, m: np.all(D[:, :2] == m[:2], 1) & (D[:, 3] == m[3])),
        ("mayor en cualquier orden dif. serie", 43374, perm),
        ("dos primeras dif. serie", 43374, lambda D, m: np.all(D[:, :2] == m[:2], 1)),
        ("primera y última dif. serie", 43374, lambda D, m: (D[:, 0] == m[0]) & (D[:, 3] == m[3])),
        ("dos últimas dif. serie", 43374, lambda D, m: np.all(D[:, 2:] == m[2:], 1)),
        ("última dif. serie", 21686, lambda D, m: D[:, 3] == m[3]),
    ]
    return dict(nombre="Lotería de Bogotá", mayor=12000e6, secos=secos, seco_dif_serie=21686,
                same=same, diff=diff, billete=18000, fracciones=3, S_obs_max=469)


def prize_matrix(plan, S, cumulative=False):
    """Matriz S x 10000 con el premio (por billete) de cada billete, para un sorteo aleatorio."""
    M = rng.integers(0, 10000); sM = rng.integers(0, S); m = NUMS[M]
    agg = np.add if cumulative else np.maximum
    v_same = np.zeros(10000); v_diff = np.zeros(10000)
    for _, val, f in plan["same"]: v_same = agg(v_same, np.where(f(NUMS, m), val, 0))
    for _, val, f in plan["diff"]: v_diff = agg(v_diff, np.where(f(NUMS, m), val, 0))
    V = np.tile(v_diff, (S, 1)); V[sM] = v_same
    V[sM, M] = plan["mayor"] if not cumulative else V[sM, M] + plan["mayor"]
    taken = {(sM, M)}
    for amt in plan["secos"]:
        while True:
            n_, s_ = rng.integers(0, 10000), rng.integers(0, S)
            if (s_, n_) not in taken: taken.add((s_, n_)); break
        col = V[:, n_].copy()
        rest = np.arange(S) != s_
        V[rest, n_] = agg(col[rest], plan["seco_dif_serie"])
        V[s_, n_] = agg(col[s_], amt)
    return V, M, sM, m


def analyze(plan, S, reps=12):
    ev_g, ev_n, ev_nf, ev_cum, p_any = [], [], [], [], []
    match = {"última cifra": ([], []), "dos últimas": ([], [])}
    contrib = {}
    for _ in range(reps):
        V, M, sM, m = prize_matrix(plan, S)
        ev_g.append(V.mean()); ev_n.append(net(V).mean())
        ev_nf.append(net(V / plan["fracciones"]).mean() * plan["fracciones"])   # comprar todas las fracciones por separado
        p_any.append((V > 0).mean())
        Vc, *_ = prize_matrix(plan, S, cumulative=True); ev_cum.append(Vc.mean())
        last = NUMS[:, 3] == m[3]; last2 = np.all(NUMS[:, 2:] == m[2:], 1)
        N = net(V)
        match["última cifra"][0].append(N[:, last].mean()); match["última cifra"][1].append(N[:, ~last].mean())
        match["dos últimas"][0].append(N[:, last2].mean()); match["dos últimas"][1].append(N[:, ~last2].mean())
        vals, cnts = np.unique(V, return_counts=True)
        for v_, c_ in zip(vals, cnts): contrib[v_] = contrib.get(v_, 0) + v_ * c_ / V.size / reps
    price = plan["billete"]
    r = dict(loteria=plan["nombre"], S_supuesto=S, precio_billete=price,
             VE_bruto=np.mean(ev_g), VE_neto=np.mean(ev_n), VE_neto_comprando_fracciones=np.mean(ev_nf),
             VE_bruto_si_premios_acumulables=np.mean(ev_cum),
             retorno_bruto_pct=100 * np.mean(ev_g) / price, retorno_neto_pct=100 * np.mean(ev_n) / price,
             perdida_esperada_por_billete=price - np.mean(ev_n), prob_algun_premio=np.mean(p_any),
             prob_mayor=1 / (10000 * S), prob_algun_seco=len(plan["secos"]) / (10000 * S),
             multiplicador_necesario=price / np.mean(ev_n))
    for k, (a, b) in match.items():
        a, b = np.mean(a), np.mean(b); base = 0.1 if k == "última cifra" else 0.01
        p_star = (price - b) / (a - b)
        r[f"VE_neto_si_acierta_{k}"] = a; r[f"VE_neto_si_no_acierta_{k}"] = b
        r[f"prob_necesaria_{k}_para_equilibrio"] = p_star
        r[f"VE_neto_con_{k}_al_doble_de_lo_normal"] = 2 * base * a + (1 - 2 * base) * b
    return r, contrib


def risk_sim(plan, S, weeks=52, players=200000):
    """Distribución del resultado de comprar un billete por semana durante un año."""
    V, *_ = prize_matrix(plan, S)
    vals, cnts = np.unique(net(V), return_counts=True); probs = cnts / cnts.sum()
    draws = rng.choice(vals, size=(players, weeks), p=probs)
    res = draws.sum(1) - weeks * plan["billete"]
    return dict(semanas=weeks, gasto_total=weeks * plan["billete"], resultado_medio=res.mean(),
                resultado_mediano=float(np.median(res)), prob_terminar_ganando=float((res > 0).mean()),
                prob_perder_mas_del_80pct=float((res < -0.8 * weeks * plan["billete"]).mean()),
                percentil_99=float(np.quantile(res, 0.99)))


if __name__ == "__main__":
    rows, risks, contribs = [], [], {}
    for plan in (plan_medellin(), plan_bogota()):
        S0 = int(np.ceil((plan["S_obs_max"] + 1) / 10) * 10)
        for S in (S0, S0 - 50):   # sensibilidad al tamaño de la emisión
            r, c = analyze(plan, S); rows.append(r)
            if S == S0: contribs[plan["nombre"]] = c
        rk = risk_sim(plan, S0); rk["loteria"] = plan["nombre"]; risks.append(rk)
    R = pd.DataFrame(rows); K = pd.DataFrame(risks)
    R.to_csv(f"{OUT}/economia_valor_esperado.csv", index=False); K.to_csv(f"{OUT}/economia_riesgo.csv", index=False)
    # composición del valor esperado bruto por tipo de premio (Medellín)
    comp = {k: {str(int(v)): float(x) for v, x in sorted(c.items()) if v > 0} for k, c in contribs.items()}
    json.dump(comp, open(f"{OUT}/economia_composicion.json", "w"), indent=1)
    pd.set_option("display.width", 250)
    print(R.T.to_string()); print(K.T.to_string())
    for k, c in comp.items():
        tot = sum(c.values()); print(k, "VE bruto", round(tot));
        for v, x in sorted(c.items(), key=lambda t: -t[1])[:8]: print("   premio", v, "aporta", round(x), f"({100*x/tot:.1f}%)")
