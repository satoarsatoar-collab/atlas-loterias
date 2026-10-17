"""Modo "nube propia" (Docker, VPS, Raspberry Pi, NAS): corre el ciclo cada N horas y sirve el tablero.

Variables de entorno:
  PORT / ATLAS_PUERTO   puerto HTTP (8080)
  ATLAS_CADA_HORAS      horas entre corridas automáticas (6)
  ATLAS_DESCARGA        "si" para descargar resultados de internet, "no" para usar solo lo que usted sube ("si")
  ATLAS_TOKEN           si se define, habilita /subir para cargar CSV desde el navegador o el celular con esa clave.
                        Sin token, /subir queda desactivado. Si expone el servidor a internet, póngalo detrás de HTTPS.
"""
from __future__ import annotations

import datetime as dt
import hmac
import http.server
import json
import os
import threading
import time
import traceback

from . import pipeline
from .config import INBOX, SITE

HORAS = float(os.environ.get("ATLAS_CADA_HORAS", "6"))
PUERTO = int(os.environ.get("PORT", os.environ.get("ATLAS_PUERTO", "8080")))
DESCARGA = os.environ.get("ATLAS_DESCARGA", "si").lower() != "no"
TOKEN = os.environ.get("ATLAS_TOKEN", "")
MAX_BYTES = 5 * 1024 * 1024
_candado = threading.Lock()
_pedido = threading.Event()
_manual = threading.Event()


def correr_una_vez(descargar=DESCARGA):
    with _candado:
        try:
            e = pipeline.ejecutar(descargar=descargar)
            print(f"[ATLAS] {e['generado']} listo · {e['veredicto']['titulo']}", flush=True)
        except Exception:  # noqa: BLE001
            print("[ATLAS] la corrida falló:\n" + traceback.format_exc(), flush=True)


def bucle():
    while True:
        _pedido.wait(timeout=HORAS * 3600)
        manual = _manual.is_set(); _pedido.clear(); _manual.clear()
        correr_una_vez(descargar=DESCARGA and not manual)   # tras una carga manual no hace falta descargar


PAGINA_SUBIR = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Subir resultados · ATLAS</title>
<style>:root{color-scheme:light dark}body{font:16px/1.5 system-ui,sans-serif;max-width:560px;margin:0 auto;padding:24px 16px}
input,button{font:inherit;width:100%;margin:6px 0 14px;padding:10px;box-sizing:border-box}button{cursor:pointer}
#r{white-space:pre-wrap}</style></head><body>
<h1>Subir resultados</h1>
<p>Archivo CSV con columnas <code>loteria, fecha, tipo, numero, serie, cuantia_millones, fuente</code>
(vea <code>data/inbox/plantilla_resultados.csv</code>).</p>
<label>Clave<input id="t" type="password" autocomplete="current-password"></label>
<label>Archivo<input id="f" type="file" accept=".csv,.txt"></label>
<button id="b">Subir y recalcular</button><p id="r"></p><p><a href="/">Volver al tablero</a></p>
<script>
document.getElementById('b').onclick = async () => {
  const f = document.getElementById('f').files[0], r = document.getElementById('r');
  if (!f) { r.textContent = 'Elija un archivo.'; return; }
  r.textContent = 'Subiendo…';
  try {
    const res = await fetch('/subir', {method: 'POST', headers: {'X-Token': document.getElementById('t').value,
      'Content-Type': 'text/csv'}, body: await f.text()});
    const j = await res.json(); r.textContent = j.mensaje;
  } catch (e) { r.textContent = 'Error: ' + e; }
};
</script></body></html>"""


class Manejador(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=SITE, **k)

    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path.rstrip("/") == "/subir":
            b = PAGINA_SUBIR.encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
            return
        if self.path.rstrip("/") == "/salud":
            return self._json(200, dict(ok=True, ocupado=_candado.locked()))
        return super().do_GET()

    def do_POST(self):
        if self.path.rstrip("/") != "/subir":
            return self._json(404, dict(mensaje="No existe."))
        if not TOKEN:
            return self._json(403, dict(mensaje="La carga web está desactivada: defina ATLAS_TOKEN en el servidor."))
        if not hmac.compare_digest(self.headers.get("X-Token", ""), TOKEN):
            return self._json(403, dict(mensaje="Clave incorrecta."))
        n = int(self.headers.get("Content-Length", "0") or 0)
        if n <= 0 or n > MAX_BYTES:
            return self._json(413, dict(mensaje="Archivo vacío o mayor de 5 MB."))
        cuerpo = self.rfile.read(n)
        os.makedirs(INBOX, exist_ok=True)
        nombre = f"web_{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
        with open(os.path.join(INBOX, nombre), "wb") as f:
            f.write(cuerpo)
        _manual.set(); _pedido.set()
        return self._json(200, dict(mensaje=f"Recibido ({nombre}). El tablero se actualiza en uno o dos minutos; "
                                            "las filas rechazadas aparecen en la sección «Los datos»."))

    def log_message(self, fmt, *args):
        pass


def main():
    os.makedirs(SITE, exist_ok=True)
    if not os.path.exists(os.path.join(SITE, "index.html")):
        correr_una_vez()
    threading.Thread(target=bucle, daemon=True).start()
    if os.path.exists(os.path.join(SITE, "index.html")):
        _pedido.set()   # primera actualización en segundo plano
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", PUERTO), Manejador)
    print(f"[ATLAS] tablero en http://0.0.0.0:{PUERTO}  · carga web {'activa' if TOKEN else 'desactivada'} "
          f"· ciclo cada {HORAS:g} h", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
