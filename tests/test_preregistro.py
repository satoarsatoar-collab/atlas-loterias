"""Pre-registro del estudio: huella intacta y pruebas exactas."""
import math

from atlas import build, preregistro, store


def test_colas_exactas():
    assert preregistro.binom_sf(0, 50, 0.1) == 1.0
    assert abs(preregistro.binom_sf(1, 1, 0.1) - 0.1) < 1e-12
    assert abs(preregistro.binom_sf(2, 2, 0.5) - 0.25) < 1e-12
    assert abs(preregistro.poisson_sf(1, 2.0) - (1 - math.exp(-2))) < 1e-12
    assert abs(preregistro.poisson_sf(2, 1.0) - (1 - 2 * math.exp(-1))) < 1e-12


def test_huella_del_preregistro_intacta():
    S, _ = store.migrar_legado(escribir=False)
    t = build.construir(S)
    r = preregistro.evaluar(t["secos"], t["mayores"])
    assert r["huella_ok"] and r["huella"].startswith("babdc8d58371586d")
    assert [h["id"] for h in r["hipotesis"]] == ["H0", "H1", "H2", "H3"]
