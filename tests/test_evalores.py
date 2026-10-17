"""Validez estadística del motor: con azar puro no debe 'descubrir' nada; con un sesgo fuerte sí debe detectarlo."""
import datetime as dt
import math

import numpy as np
import pandas as pd

from atlas import patterns as P
from atlas.config import LOTERIAS


def sintetico(semanas, p4=0.10, seed=0, n_secos=40, inicio="2026-01-05"):
    rng = np.random.default_rng(seed)
    may, sec = [], []
    d0 = dt.date.fromisoformat(inicio)
    for w in range(semanas):
        for slug, (_, wd, _) in LOTERIAS.items():
            f = (d0 + dt.timedelta(days=7 * w + (wd - d0.weekday()) % 7)).isoformat()
            may.append(dict(slug=slug, fecha=f, numero=f"{rng.integers(10000):04d}"))
            nums = rng.integers(0, 10000, n_secos)
            if slug == "loteria-de-medellin" and p4 > 0.10:
                forzar = rng.random(n_secos) < (p4 - 0.1) / 0.9
                nums[forzar] = nums[forzar] // 10 * 10 + 4
            sec += [dict(slug=slug, fecha=f, fila=i + 1, numero=f"{x:04d}", clase="seco", menor_cuantia=False)
                    for i, x in enumerate(nums)]
    return pd.DataFrame(may), pd.DataFrame(sec)


def test_probabilidades_nulas_exactas():
    assert abs(P.P_ESTR.sum() - 1) < 1e-12 and abs(P.P_SUMA.sum() - 1) < 1e-12 and abs(P.P_PARES.sum() - 1) < 1e-12
    r = P.rasgos([f"{i:04d}" for i in range(10000)])          # enumeración completa
    assert np.allclose(np.bincount(r["estructura"], minlength=5) / 1e4, P.P_ESTR)
    assert np.allclose(np.bincount(r["suma"], minlength=37) / 1e4, P.P_SUMA)
    assert np.allclose(np.bincount(r["pares"], minlength=5) / 1e4, P.P_PARES)


def test_azar_puro_no_valida_nada():
    """Ville: con azar, a lo sumo 1 de cada 20 patrones debería superar E = 20. Y e-BH no debe validar ninguno."""
    fr, medias = [], []
    for seed in (1, 2):
        m, s = sintetico(12, seed=seed)
        M = P.Motor(m, s, inicio_prospectivo="2026-01-05").correr()
        R = P.tablas(M)
        E = 10 ** R["patrones"].log10E_prosp
        fr.append((E >= 20).mean()); medias.append(E.mean())
        assert R["resumen"]["validados"] == []
    assert max(fr) <= 0.05
    assert np.mean(medias) < 1.5


def test_detecta_un_sesgo_fuerte():
    """Si el 4 sale el 30 % de las veces como última cifra en Medellín, el combinador de esa lotería lo nota."""
    m, s = sintetico(12, p4=0.30, seed=3)
    M = P.Motor(m, s, inicio_prospectivo="2026-01-05").correr()
    T = P.tablas(M)["patrones"].set_index("id")
    assert T.loc["comb|seco|loteria-de-medellin|d4", "log10E_prosp"] > math.log10(20)
    assert any("medellin" in i and "d4" in i for i in P.tablas(M)["resumen"]["validados"])
    pred = M.predecir("seco", "loteria-de-medellin", "2026-04-03")
    assert pred["ultima_cifra"][0]["cifra"] == 4


def test_sin_mirar_el_futuro():
    """La predicción de un sorteo no cambia si se agregan sorteos posteriores."""
    m, s = sintetico(6, seed=5)
    corte = "2026-01-30"
    M1 = P.Motor(m[m.fecha <= corte], s[s.fecha <= corte]).correr()
    M2 = P.Motor(m, s).correr()
    a = [x for x in M1.aciertos if x["fecha"] <= corte]
    b = [x for x in M2.aciertos if x["fecha"] <= corte]
    assert a == b
