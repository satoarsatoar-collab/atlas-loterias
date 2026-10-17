"""Clasificación de filas que no son extracciones independientes."""
import pandas as pd

from atlas import build, store


def test_clases_de_derivados():
    filas = [dict(slug="loteria-de-medellin", fecha="2026-10-09", sorteo="4858", tipo="mayor", numero="1234", serie="050")]
    secos = [("4321", "050"), ("1235", "050"), ("5678", "100"), ("8765", "100"), ("5678", "100"), ("1111", "000"),
             ("2222", ""), ("9999", "321"), ("1234", "051")]
    for i, (n, s) in enumerate(secos, 1):
        filas.append(dict(slug="loteria-de-medellin", fecha="2026-10-09", sorteo="4858", tipo="seco", fila=str(i),
                          numero=n, serie=s, fuente="prueba"))
    S = store.incorporar(store.vacio(), pd.DataFrame(filas), store.Reporte())
    t = build.construir(S)
    clases = t["secos"].sort_values("fila").clase.tolist()
    assert clases == ["derivado_permutacion_mayor", "derivado_mayor_pm1", "seco", "derivado_permutacion_seco",
                      "duplicado_en_sorteo", "serie_000_ambigua", "serie_faltante", "seco", "seco"]


def test_migracion_reproduce_el_estudio():
    """El almacén migrado debe dar exactamente las mismas clases que el estudio original."""
    import os
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    orig = pd.read_csv(os.path.join(raiz, "estudio", "data", "processed", "secos.csv"), dtype=str, keep_default_na=False)
    S, _ = store.migrar_legado(escribir=False)
    t = build.construir(S)
    n = t["secos"]
    assert (n.clase == "seco").sum() == (orig.clase == "seco").sum() == 4809
    o = orig.assign(k=orig.groupby(["slug", "fecha", "numero", "serie"]).cumcount())
    n = n.assign(k=n.groupby(["slug", "fecha", "numero", "serie"]).cumcount())
    m = o.merge(n, on=["slug", "fecha", "numero", "serie", "k"], suffixes=("_o", "_n"))
    assert len(m) == len(o) and (m.clase_o == m.clase_n).all()
