"""Validez estadística del motor: con azar puro no debe 'descubrir' nada; con un sesgo fuerte sí debe detectarlo."""
import datetime as dt
import math

import numpy as np
import pandas as pd

from atlas import patterns as P
from atlas.config import LOTERIAS


def sintetico(semanas, p4=0.10, seed=0, n_secos=40, inicio="2026-08-17", franja0=0.0):
    """Sorteos simulados. p4: probabilidad de que un seco de Medellín termine en 4 (0,10 = azar).
    franja0: fracción extra de secos de Medellín con serie en la primera franja (001-049)."""
    from atlas.config import SERIES_EMISION
    rng = np.random.default_rng(seed)
    may, sec = [], []
    d0 = dt.date.fromisoformat(inicio)
    for w in range(semanas):
        for slug, (_, wd, _) in LOTERIAS.items():
            S = SERIES_EMISION[slug]
            f = (d0 + dt.timedelta(days=7 * w + (wd - d0.weekday()) % 7)).isoformat()
            may.append(dict(slug=slug, fecha=f, numero=f"{rng.integers(10000):04d}", serie=f"{rng.integers(S):03d}"))
            nums = rng.integers(0, 10000, n_secos)
            ser = rng.integers(1, S, n_secos)
            if slug == "loteria-de-medellin" and p4 > 0.10:
                forzar = rng.random(n_secos) < (p4 - 0.1) / 0.9
                nums[forzar] = nums[forzar] // 10 * 10 + 4
            if slug == "loteria-de-medellin" and franja0 > 0:
                forzar = rng.random(n_secos) < franja0
                ser[forzar] = rng.integers(1, S // 10, forzar.sum())
            sec += [dict(slug=slug, fecha=f, fila=i + 1, numero=f"{x:04d}", serie=f"{y:03d}", clase="seco", menor_cuantia=False)
                    for i, (x, y) in enumerate(zip(nums, ser))]
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
        M = P.Motor(m, s, inicio_prospectivo="2026-08-17").correr()
        R = P.tablas(M)
        E = 10 ** R["patrones"].log10E_prosp
        fr.append((E >= 20).mean()); medias.append(E.mean())
        assert R["resumen"]["validados"] == []
    assert max(fr) <= 0.05
    assert np.mean(medias) < 1.5


def test_detecta_un_sesgo_fuerte():
    """Si el 4 sale el 30 % de las veces como última cifra en Medellín, el combinador de esa lotería lo nota."""
    m, s = sintetico(12, p4=0.30, seed=3)
    M = P.Motor(m, s, inicio_prospectivo="2026-08-17").correr()
    T = P.tablas(M)["patrones"].set_index("id")
    assert T.loc["comb|seco|loteria-de-medellin|d4", "log10E_prosp"] > math.log10(20)
    assert any("medellin" in i and "d4" in i for i in P.tablas(M)["resumen"]["validados"])
    pred = M.predecir("seco", "loteria-de-medellin", "2026-11-13")
    assert pred["ultima_cifra"][0]["cifra"] == 4


def test_sin_mirar_el_futuro():
    """La predicción de un sorteo no cambia si se agregan sorteos posteriores."""
    m, s = sintetico(6, seed=5)
    corte = "2026-09-11"
    M1 = P.Motor(m[m.fecha <= corte], s[s.fecha <= corte]).correr()
    M2 = P.Motor(m, s).correr()
    a = [x for x in M1.aciertos if x["fecha"] <= corte]
    b = [x for x in M2.aciertos if x["fecha"] <= corte]
    assert a == b
    a = [x for x in M1.metodos_res if x["fecha"] <= corte]
    b = [x for x in M2.metodos_res if x["fecha"] <= corte]
    assert a == b and len(a) > 0


def test_listas_de_numeros_posibles():
    m, s = sintetico(4, seed=9)
    M = P.Motor(m, s).correr()
    p = M.predecir("seco", "loteria-de-medellin", "2026-09-18")
    assert set(p["listas"]) == set(P.METODOS)
    for k, v in p["listas"].items():
        assert len(v) == len(set(v)) <= 10 and all(len(x) == 4 and x.isdigit() for x in v), k
    ultimo = m[m.slug == "loteria-de-medellin"].sort_values("fecha").numero.iloc[-1]
    assert p["listas"]["mayor_anterior"][0] == ultimo
    assert P.Motor.lista_azar("loteria-de-medellin", "2026-09-18") == p["listas"]["azar"]   # reproducible
    assert len(p["q_posiciones"]) == 4 and all(abs(sum(q) - 1) < 1e-3 for q in p["q_posiciones"])


def test_series_nulo_exacto_y_listas():
    m, s = sintetico(3, seed=11)
    M = P.Motor(m, s)
    for slug in M.lots:
        for r in P.SERIE_RASGOS:
            K, p0, _ = M.info(r, "seco", slug)
            assert abs(p0.sum() - 1) < 1e-12 and len(p0) == K
        assert M.info("serie", "seco", slug)[1][0] == 0        # la serie 000 no cuenta en los secos
    M.correr()
    p = M.predecir("seco", "loteria-de-medellin", "2026-09-11")
    ls = p["listas_series"]
    assert len(ls["series_combinador"]) == 10 and len(set(ls["series_azar"])) == 10
    assert all("001" <= x <= f"{p['series_en_juego'] - 1:03d}" for x in ls["series_combinador"] + ls["series_azar"])


def test_detecta_series_cargadas():
    """Si un tercio extra de los secos de Medellín cae en la franja 001-049, el combinador de franjas lo nota."""
    m, s = sintetico(12, seed=4, franja0=0.30)
    M = P.Motor(m, s, inicio_prospectivo="2026-08-17").correr()
    T = P.tablas(M)["patrones"].set_index("id")
    assert T.loc["comb|seco|loteria-de-medellin|serie_franja", "log10E_prosp"] > math.log10(20)
    from atlas import series
    r = {f["slug"]: f for f in series.analizar(M)["loterias"]}
    assert r["loteria-de-medellin"]["veredicto"].startswith("desigual")
    assert sum(f.get("veredicto", "").startswith("desigual") for f in r.values()) == 1
