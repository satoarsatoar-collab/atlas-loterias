"""Carga de archivos: ceros a la izquierda, alias, formatos de fecha y cuantía, rechazos y no duplicar."""
import pandas as pd

from atlas import ingest, store


def _df(rows):
    return pd.DataFrame(rows, dtype=str)


def test_normaliza_ceros_alias_fechas_y_cuantias():
    df = _df([
        dict(Lotería="Lotería de Medellín", Fecha="09/10/2026", Tipo="Seco", Número="47", Serie="3", Cuantía="$10.000.000"),
        dict(Lotería="medellin", Fecha="2026-10-09", Tipo="mayor", Número="0123", Serie="045", Cuantía=""),
        dict(Lotería="Bogota", Fecha="2026-10-08", Tipo="", Número="5821.0", Serie="190", Cuantía="40 millones"),
    ])
    ok, malas, avisos = ingest.normalizar(df, "x.csv")
    assert not malas
    assert ok.slug.tolist() == ["loteria-de-medellin", "loteria-de-medellin", "loteria-de-bogota"]
    assert ok.numero.tolist() == ["0047", "0123", "5821"]
    assert ok.serie.tolist() == ["003", "045", "190"]
    assert ok.tipo.tolist() == ["seco", "mayor", "seco"]
    assert ok.cuantia_millones.tolist() == ["10", "", "40"]
    assert any("ceros" in a for a in avisos)


def test_rechaza_con_motivo():
    df = _df([dict(loteria="Lotería de Narnia", fecha="2026-13-40", tipo="otro", numero="12345", serie="ab")])
    ok, malas, _ = ingest.normalizar(df, "y.csv")
    assert ok.empty and len(malas) == 1
    m = malas[0]["motivo"]
    for palabra in ("lotería desconocida", "fecha ilegible", "tipo desconocido", "número inválido", "serie inválida"):
        assert palabra in m


def test_faltan_columnas():
    ok, malas, _ = ingest.normalizar(_df([dict(fecha="2026-10-09")]), "z.csv")
    assert ok.empty and "faltan columnas" in malas[0]["motivo"]


def test_no_duplica_y_completa_cuantia():
    base = _df([dict(loteria="Medellín", fecha="2026-10-09", tipo="mayor", numero="1271", serie="087"),
                dict(loteria="Medellín", fecha="2026-10-09", tipo="seco", numero="0060", serie="113"),
                dict(loteria="Medellín", fecha="2026-10-09", tipo="seco", numero="2369", serie="073")])
    ok, _, _ = ingest.normalizar(base, "a.csv")
    rep = store.Reporte()
    S = store.incorporar(store.vacio(), ok, rep)
    assert len(S) == 3 and rep.agregadas == 3
    S = store.incorporar(S, ok, rep)                     # la misma carga otra vez
    assert len(S) == 3
    con_cuantia = _df([dict(loteria="Medellín", fecha="2026-10-09", tipo="seco", numero="0060", serie="113",
                            cuantia_millones="10", fuente="Telemedellín")])
    ok2, _, _ = ingest.normalizar(con_cuantia, "b.csv")
    rep2 = store.Reporte()
    S = store.incorporar(S, ok2, rep2)
    assert len(S) == 3 and rep2.cuantias == 1
    assert S[S.numero == "0060"].cuantia_millones.iloc[0] == "10"


def test_conflicto_de_mayor_conserva_el_guardado():
    a, _, _ = ingest.normalizar(_df([dict(loteria="Cauca", fecha="2026-10-10", tipo="mayor", numero="1111", serie="001")]), "a")
    b, _, _ = ingest.normalizar(_df([dict(loteria="Cauca", fecha="2026-10-10", tipo="mayor", numero="2222", serie="002")]), "b")
    rep = store.Reporte()
    S = store.incorporar(store.incorporar(store.vacio(), a, rep), b, rep)
    assert S.numero.tolist() == ["1111"] and len(rep.conflictos) == 1
