"""Descarga: se prueba contra una página SINTÉTICA con el formato observado (no contra el sitio en vivo)."""
import datetime as dt
import os

from atlas import scrape, store

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "loteriaya_resultado_sintetico.html")


def test_parsea_mayor_y_secos():
    p = scrape.parsear(open(FIX, encoding="utf-8").read())
    assert (p["sorteo"], p["numero"], p["serie"]) == ("4857", "1271", "087")
    assert p["secos"][:2] == [("0060", "113"), ("2369", "073")] and len(p["secos"]) == 6


def test_formato_desconocido_falla_con_mensaje():
    try:
        scrape.parsear("<html>mantenimiento</html>")
    except ValueError as e:
        assert "frase del número ganador" in str(e)
    else:
        raise AssertionError("debió fallar")


def test_descarga_con_cliente_simulado():
    html = open(FIX, encoding="utf-8").read()
    pedidas = []

    def obtener(url):
        pedidas.append(url)
        if url.endswith("/loteria/loteria-de-medellin"):
            return '<a href="/loteria/loteria-de-medellin/resultado/2026-10-16">x</a>'
        if url.endswith("/resultado/2026-10-16") and "medellin" in url:
            return html
        if "/resultado/" in url:
            return None
        raise ConnectionError("sin red en la prueba")

    S, info = scrape.descargar(store.vacio(), hoy=dt.date(2026, 10, 17), pausa=0, obtener=obtener)
    med = S[S.slug == "loteria-de-medellin"]
    assert info["sorteos_nuevos"] == 1 and len(med) == 7
    assert med[med.tipo == "mayor"].numero.iloc[0] == "1271"
    assert any("página principal no disponible" in e for e in info["errores"])   # las demás fallaron sin romper nada
