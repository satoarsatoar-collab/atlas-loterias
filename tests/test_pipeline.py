"""De punta a punta en una copia temporal del repositorio: migrar, cargar un archivo, recalcular, no duplicar."""
import json
import os
import shutil
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_ciclo_completo(tmp_path):
    dst = tmp_path / "repo"
    shutil.copytree(RAIZ, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", "site", "state", "store", "procesados"))
    (dst / "data" / "inbox" / "nuevos.csv").write_text(
        "loteria,fecha,tipo,numero,serie,cuantia_millones,fuente\n"
        "Boyacá,2026-10-17,mayor,4321,111,,prueba\n"
        "Boyacá,2026-10-17,seco,47,3,10,prueba\n"
        "Boyacá,2026-10-17,seco,5821,190,,prueba\n"
        "Narnia,2026-10-17,seco,1111,111,,prueba\n", encoding="utf-8")
    run = lambda: subprocess.run([sys.executable, "-m", "atlas.pipeline", "--scrape", "no"], cwd=dst,
                                 capture_output=True, text=True, timeout=600)
    r = run(); assert r.returncode == 0, r.stderr
    e = json.load(open(dst / "site" / "estado.json", encoding="utf-8"))
    assert e["datos"]["ultimo_dato"] == "2026-10-17"
    assert len(e["ingesta"]["rechazos"]) == 1 and "Narnia" in e["ingesta"]["rechazos"][0]["motivo"]
    assert e["premios_prospectivos"] == 3                    # 1 mayor + 2 secos posteriores al inicio prospectivo
    assert (dst / "site" / "index.html").exists() and (dst / "state" / "RESUMEN.md").exists()
    assert list((dst / "state" / "predicciones").glob("*.json.sha256"))
    filas = (dst / "data" / "store" / "resultados.csv").read_text(encoding="utf-8").count("\n")
    assert not (dst / "data" / "inbox" / "nuevos.csv").exists()
    r = run(); assert r.returncode == 0, r.stderr               # segunda corrida: nada se duplica
    assert (dst / "data" / "store" / "resultados.csv").read_text(encoding="utf-8").count("\n") == filas
    assert "0047" in (dst / "data" / "store" / "resultados.csv").read_text(encoding="utf-8")
