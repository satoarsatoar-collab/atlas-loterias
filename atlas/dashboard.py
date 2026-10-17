"""Tablero estático (site/index.html): un solo archivo, sin dependencias externas, modo claro y oscuro."""
from __future__ import annotations

import datetime as dt
import html
import json
import math

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def e(x) -> str:
    return html.escape(str(x), quote=True)


def n_es(x, dec=0) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    s = f"{x:,.{dec}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def E_txt(log10E) -> str:
    if log10E is None:
        return "—"
    v = 10 ** log10E
    if v < 0.01: return "< 0,01"
    if v < 10: return n_es(v, 2)
    if v < 1e6: return n_es(v, 0)
    return "> 1 millón"


def fecha_corta(f: str) -> str:
    d = dt.date.fromisoformat(f[:10])
    return f"{d.day} {MESES[d.month - 1]}"


def fecha_larga(f: str) -> str:
    d = dt.date.fromisoformat(f[:10])
    dias = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
    return f"{dias[d.weekday()]} {d.day} {MESES[d.month - 1]} {d.year}"


# --------------------------------------------------------------------------------------------- gráficos SVG
def svg_lineas(series, *, log=False, umbrales=(), marca=None, alto=290, etiqueta_y=""):
    """series: [dict(nombre, color, puntos=[(fecha, y)], punteada=False)]"""
    pts = [(dt.date.fromisoformat(f).toordinal(), y) for s in series for f, y in s["puntos"]]
    if not pts:
        return '<p class="vacio">Todavía no hay datos para este gráfico.</p>'
    W, H, l, r, t, b = 760, alto, 68, 18, 14, 34
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts] + [u[0] for u in umbrales]
    x0, x1 = min(xs), max(xs)
    if x0 == x1: x0 -= 1; x1 += 1
    y0, y1 = min(ys), max(ys)
    if log:
        y0, y1 = math.floor(max(min(y0, -1), -6)), math.ceil(max(y1, 1.5))
    else:
        y0 = min(0, y0); y1 = y1 * 1.08 if y1 > 0 else 1
    X = lambda v: l + (v - x0) / (x1 - x0) * (W - l - r)
    Y = lambda v: t + (1 - (v - y0) / (y1 - y0)) * (H - t - b)
    o = [f'<div class="graf-env"><svg viewBox="0 0 {W} {H}" role="img" aria-label="{e(etiqueta_y)}" class="graf">']
    if log:
        ticks = list(range(int(y0), int(y1) + 1))
        if len(ticks) > 9:
            ticks = [k for k in ticks if k % 2 == 0]
        sup = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")
        lab = lambda k: (n_es(10 ** k, 0) if k <= 6 else "10" + str(k).translate(sup)) if k >= 0 else \
            (n_es(10 ** k, -k) if k >= -3 else "10" + str(k).translate(sup))
    else:
        paso = max(1, round((y1 - y0) / 5)); mag = 10 ** math.floor(math.log10(paso)); paso = math.ceil(paso / mag) * mag
        ticks = [y0 + i * paso for i in range(int((y1 - y0) / paso) + 1)]
        lab = lambda k: n_es(k, 0)
    for k in ticks:
        o.append(f'<line x1="{l}" x2="{W - r}" y1="{Y(k):.1f}" y2="{Y(k):.1f}" class="grid"/>'
                 f'<text x="{l - 8}" y="{Y(k) + 4:.1f}" class="eje" text-anchor="end">{lab(k)}</text>')
    if log and y0 <= 0 <= y1:
        o.append(f'<line x1="{l}" x2="{W - r}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" class="base"/>')
    n_t = 5; span = x1 - x0
    for i in range(n_t + 1):
        v = x0 + span * i / n_t
        f = dt.date.fromordinal(int(round(v))).isoformat()
        anc = "start" if i == 0 else ("end" if i == n_t else "middle")
        o.append(f'<text x="{X(v):.1f}" y="{H - 10}" class="eje" text-anchor="{anc}">{fecha_corta(f)}</text>')
    if marca and x0 <= dt.date.fromisoformat(marca[0]).toordinal() <= x1:
        mx = X(dt.date.fromisoformat(marca[0]).toordinal())
        o.append(f'<line x1="{mx:.1f}" x2="{mx:.1f}" y1="{t}" y2="{H - b}" class="umbral"/>'
                 f'<text x="{mx + 6:.1f}" y="{t + 12}" class="eje">{e(marca[1])}</text>')
    for v, txt in umbrales:
        o.append(f'<line x1="{l}" x2="{W - r}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="umbral"/>'
                 f'<text x="{l + 6}" y="{Y(v) - 5:.1f}" class="eje">{e(txt)}</text>')
    for s in series:
        P = [(X(dt.date.fromisoformat(f).toordinal()), Y(max(y, y0)), f, y) for f, y in s["puntos"]]
        if not P:
            continue
        d = " ".join(f"{a:.1f},{c:.1f}" for a, c, _, _ in P)
        dash = ' stroke-dasharray="6 5"' if s.get("punteada") else ""
        o.append(f'<polyline points="{d}" fill="none" stroke="{s["color"]}" stroke-width="2" '
                 f'stroke-linejoin="round" stroke-linecap="round"{dash}/>')
        a, c, _, _ = P[-1]
        o.append(f'<circle cx="{a:.1f}" cy="{c:.1f}" r="4" fill="{s["color"]}" stroke="var(--surface)" stroke-width="2"/>')
        for a, c, f, y in P:
            val = E_txt(y) if log else n_es(y, 1)
            o.append(f'<circle cx="{a:.1f}" cy="{c:.1f}" r="7" class="hit"><title>{fecha_larga(f)} · '
                     f'{e(s["nombre"][:70])}: {"E = " if log else ""}{val}</title></circle>')
    o.append("</svg></div>")
    return "".join(o)


def leyenda(series):
    items = []
    for s in series:
        estilo = "border-top-style:dashed" if s.get("punteada") else ""
        items.append(f'<span class="ley"><i style="border-color:{s["color"]};{estilo}"></i>{e(s["nombre"])}</span>')
    return f'<div class="leyenda">{"".join(items)}</div>'


# --------------------------------------------------------------------------------------------- piezas
def kpi(titulo, valor, nota=""):
    return (f'<div class="kpi"><div class="kpi-t">{e(titulo)}</div><div class="kpi-v">{valor}</div>'
            f'<div class="kpi-n">{nota}</div></div>')


def tabla(cab, filas, clase=""):
    th = "".join(f"<th>{c}</th>" for c in cab)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas)
    return f'<div class="tabla-env"><table class="{clase}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>'


ICONO = {"senal": "▲", "observacion": "◆", "inicio": "●", "azar": "■"}
ETIQUETA = {"senal": "Señal", "observacion": "En observación", "inicio": "Comenzando", "azar": "Azar"}


def estado_chip(est):
    c = {"validado": "ok", "validado (prueba principal)": "ok", "en observación": "obs", "se sostiene": "obs",
         "se rechaza H0: hay señal": "obs"}.get(est, "neutro")
    return f'<span class="chip {c}">{e(est)}</span>'


# --------------------------------------------------------------------------------------------- números posibles
def _marca(r):
    return f"{r['aciertos']} de {n_es(r['esperado'], 1)}" if r["premios"] else "—"


def seccion_numeros(S: dict) -> str:
    preds = [p for p in S["proximos"] if p["tipo"] == "seco" and p.get("listas")]
    mayores = {(p["slug"], p["fecha"]): p for p in S["proximos"] if p["tipo"] == "mayor"}
    metodos = {m["id"]: m for m in S.get("metodos", [])}
    prom = {c["slug"]: (c["secos_independientes"] / c["con_secos"]) if c["con_secos"] else 40 for c in S["cobertura"]}
    if not preds:
        return '<section id="numeros"><h2>Números posibles</h2><p class="vacio">No hay sorteos pendientes en los próximos 8 días.</p></section>'
    opciones, bloques, datos_q, datos_l, nombres = [], [], {}, {}, {}
    for i, p in enumerate(preds):
        pid = f"{p['slug']}|{p['fecha']}"
        nom = f"{p['loteria']} · {fecha_larga(p['fecha'])[:-5]}"
        opciones.append(f'<option value="{e(pid)}">{e(nom)}</option>')
        datos_q[pid] = p.get("q_posiciones"); datos_l[pid] = p["listas"]; nombres[pid] = nom
        n = prom.get(p["slug"], 40)
        prob = 100 * (1 - (1 - 10 / 1e4) ** n)
        may = mayores.get((p["slug"], p["fecha"]))
        u = p["ultima_cifra"][0]
        tarjetas = []
        for mid, lst in p["listas"].items():
            m = metodos.get(mid, dict(nombre=mid, descripcion="", historial=dict(premios=0), nuevos=dict(premios=0)))
            chips = "".join(f'<span class="num">{e(x)}</span>' for x in lst) or '<span class="tenue">sin datos</span>'
            nuevos = f" En datos nuevos: {_marca(m['nuevos'])}." if m["nuevos"]["premios"] else ""
            tarjetas.append(f'<div class="met{" met-control" if mid == "azar" else ""}"><div class="met-t">{e(m["nombre"])}</div>'
                            f'<div class="met-d">{e(m["descripcion"])}</div><div class="chips">{chips}</div>'
                            f'<div class="met-r">Historial, 14 loterías: {m["historial"]["aciertos"] if m["historial"]["premios"] else "—"} '
                            f'aciertos; el azar daba {n_es(m["historial"].get("esperado", 0), 1)}.{nuevos}</div></div>')
        cab = (f'<p class="sorteo-cab"><b>{e(p["loteria"])}</b>, {e(fecha_larga(p["fecha"]))}. '
               f'Premio mayor (5 del combinador): <span class="mono">{" ".join(may["top_numeros"]) if may else "—"}</span> · '
               f'última cifra más probable para los secos: <b>{u["cifra"]}</b> ({n_es(100 * u["prob"], 1)} % frente a 10 %) · '
               f'terminaciones: <span class="mono">{" ".join(t["t2"] for t in p["terminaciones"][:3])}</span>.<br>'
               f'<span class="tenue">Con unos {n_es(n)} secos por sorteo, cualquier lista de 10 números tiene un {n_es(prob, 1)} % de '
               f'que al menos uno salga (con cualquier serie).</span></p>')
        bloques.append(f'<div class="sorteo" data-id="{e(pid)}"{"" if i == 0 else " hidden"}>{cab}'
                       f'<div class="metodos">{"".join(tarjetas)}</div></div>')
    filas = []
    for m in S.get("metodos", []):
        filas.append([f"<b>{e(m['nombre'])}</b>", _marca(m["historial"]), _marca(m["nuevos"]), _marca(m["registrado"]),
                      f'<span class="mono">{e(m["historial"]["numeros"] or "—")}</span>'])
    c = S.get("consulta", {})
    datos = dict(numeros=c.get("numeros", {}), total_secos=c.get("total_secos", 0), total_mayores=c.get("total_mayores", 0),
                 secos_desde=c.get("secos_desde", ""), mayores_desde=c.get("mayores_desde", ""), q=datos_q, listas=datos_l,
                 nombres=nombres, metodos={k: v["nombre"] for k, v in metodos.items()})
    js_datos = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f"""<section id="numeros"><h2>Números posibles</h2>
<p class="aviso"><b>Antes de usarlos:</b> ningún método ha demostrado acertar más que el azar. Cada número de 4 cifras tiene
1 entre 10.000 de salir en cada premio, esté en una lista o no. «Acertar» aquí significa que el número salió en un seco
con <i>cualquier</i> serie; para cobrar un seco hace falta además la serie exacta. La lista «al azar» está para comparar:
si con el tiempo los demás métodos no le ganan, no son mejores que escoger a ciegas.</p>
<label class="sel">Sorteo <select id="sel-sorteo">{"".join(opciones)}</select></label>
{"".join(bloques)}
<h3>Marcador: ¿algún método le gana al azar?</h3>
<p class="nota">Aciertos de cada lista de 10 números frente a los esperados por pura suerte. Con tan pocos aciertos,
diferencias de 2 o 3 son ruido normal. «Guardadas» son las listas publicadas con huella digital antes de cada sorteo.</p>
{tabla(['Método', 'Historial', 'Datos nuevos', 'Guardadas', 'Números que acertaron (historial)'], filas)}
<h3>Consulte un número</h3>
<form id="form-num" class="consulta" autocomplete="off"><input id="in-num" inputmode="numeric" pattern="[0-9]{{1,4}}"
maxlength="4" placeholder="Ej. 0047" aria-label="Número de 4 cifras"><button type="submit">Consultar</button></form>
<p id="res-num" class="res-num" aria-live="polite"></p>
<script id="datos-numeros" type="application/json">{js_datos}</script>
</section>"""


JS = """<script>
(function () {
  var el = document.getElementById('datos-numeros');
  if (!el) return;
  var D = JSON.parse(el.textContent);
  var MESES = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
  var fecha = function (f) { var p = f.split('-'); return +p[2] + ' ' + MESES[+p[1] - 1] + ' ' + p[0]; };
  var num = function (x, d) { return x.toLocaleString('es-CO', {minimumFractionDigits: d, maximumFractionDigits: d}); };
  var sel = document.getElementById('sel-sorteo');
  function mostrar() {
    document.querySelectorAll('.sorteo').forEach(function (x) { x.hidden = x.dataset.id !== sel.value; });
    try { localStorage.setItem('atlas-sorteo', sel.value); } catch (e) {}
  }
  if (sel) {
    try { var v = localStorage.getItem('atlas-sorteo'); if (v && D.listas[v]) sel.value = v; } catch (e) {}
    sel.addEventListener('change', mostrar); mostrar();
  }
  var form = document.getElementById('form-num'), out = document.getElementById('res-num');
  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var t = document.getElementById('in-num').value.trim();
    if (!/^[0-9]{1,4}$/.test(t)) { out.textContent = 'Escriba un número de hasta 4 cifras.'; return; }
    var n = ('0000' + t).slice(-4), r = D.numeros[n] || [0, 0, null, null, null];
    var es = D.total_secos / 1e4, em = D.total_mayores / 1e4;
    var txt = 'El ' + n + ' ha salido ' + r[0] + (r[0] === 1 ? ' vez' : ' veces') + ' como seco (desde el ' + fecha(D.secos_desde) +
      ') y ' + r[1] + (r[1] === 1 ? ' vez' : ' veces') + ' como premio mayor (desde el ' + fecha(D.mayores_desde) + '). ';
    txt += 'Un número cualquiera sale en promedio ' + num(es, 2) + ' veces como seco y ' + num(em, 2) + ' como mayor en esos periodos. ';
    if (r[2]) txt += 'Última vez: ' + r[3] + ', ' + fecha(r[2]) + ' (' + (r[4] === 's' ? 'seco' : 'premio mayor') + '). ';
    var id = sel ? sel.value : null, q = id && D.q[id];
    if (q) {
      var f = 1; for (var i = 0; i < 4; i++) f *= q[i][+n[i]] / 0.1;
      var en = Object.keys(D.listas[id]).filter(function (k) { return D.listas[id][k].indexOf(n) >= 0; })
        .map(function (k) { return D.metodos[k] || k; });
      txt += 'Para ' + D.nombres[id] + ', el combinador le da ' + num(f, 2) + ' veces la probabilidad del azar (no validado)' +
        (en.length ? ' y aparece en: ' + en.join(', ') + '.' : '; no aparece en ninguna lista.');
    }
    out.textContent = txt;
  });
})();
</script>"""


# --------------------------------------------------------------------------------------------- página
def render(S: dict) -> str:
    v = S["veredicto"]; d = S["datos"]; m = S["motor"]; P = S.get("principal", {})
    hay_p = S["premios_prospectivos"] > 0
    out = []
    out.append(f"""<header>
<p class="sup">ATLAS · laboratorio estadístico de loterías colombianas</p>
<h1>¿Hay algún patrón que le gane al azar?</h1>
<p class="sub">Actualizado {e(fecha_larga(S['generado']))}, {e(S['generado'][11:16])} (hora de Colombia) ·
último sorteo con datos: {e(fecha_larga(d['ultimo_dato']))}</p>
</header>
<section class="veredicto v-{e(v['nivel'])}">
<div class="v-et"><span aria-hidden="true">{ICONO[v['nivel']]}</span> {ETIQUETA[v['nivel']]}</div>
<h2>{e(v['titulo'])}</h2><p>{e(v['texto'])}</p></section>""")

    ac = S.get("aciertos", {}); acp = ac.get("prospectivo") or ac.get("retrospectivo") or {}
    fase_ac = "en datos nuevos" if ac.get("prospectivo") else "retrospectivo"
    mejor = S["top_patrones"][0] if S["top_patrones"] else {}
    col = "log10E_prosp" if hay_p else "log10E_total"
    out.append('<section class="kpis">' + "".join([
        kpi("Premios guardados", n_es(d["secos_independientes"] + d["mayores"]),
            f"{n_es(d['secos_independientes'])} secos independientes y {n_es(d['mayores'])} premios mayores"),
        kpi("Seguimiento en datos nuevos", f"{S['dias_prospectivos']} días",
            f"{n_es(S['premios_prospectivos'])} premios desde el {fecha_corta(S['inicio_prospectivo'])}"),
        kpi("Patrones vigilados", n_es(m["reglas"] + m["combinadores"]),
            f"{n_es(m['reglas'])} reglas y {n_es(m['combinadores'])} combinaciones"),
        kpi("Combinador principal", f"E = {E_txt(P.get(col))}",
            ("en datos nuevos" if hay_p else "retrospectivo") + f" · se valida con E ≥ {n_es(S['umbral_observacion'])}"),
        kpi("Aciertos del top-10", f"{acp.get('aciertos', 0)} de {n_es(acp.get('esperado', 0), 1)}",
            f"observados frente a esperados por azar ({fase_ac})"),
    ]) + "</section>")

    out.append(seccion_numeros(S))

    # ---------------------------------------------------------------- evidencia en el tiempo
    colores = ["var(--s1)", "var(--s2)", "var(--s3)"]
    series = [dict(nombre=s["nombre"], color=colores[i], puntos=s["puntos"]) for i, s in enumerate(S["trayectorias"]["series"])]
    if series:
        series[0]["nombre"] = "Combinador principal (números de los secos, todas las loterías)"
    thr = [(math.log10(S["umbral_observacion"]), f"E = {n_es(S['umbral_observacion'])}: en observación"),
           (math.log10(m["umbral_eBH_un_descubrimiento"]), f"E = {n_es(m['umbral_eBH_un_descubrimiento'])}: validado entre todos (e-BH)")]
    titulo_g = "Evidencia acumulada en datos nuevos" if hay_p else "Evidencia acumulada (retrospectiva: datos ya mirados)"
    filas_t = []
    for s in series:
        for f, y in s["puntos"][-8:]:
            filas_t.append([e(s["nombre"][:60]), fecha_corta(f), E_txt(y)])
    out.append(f"""<section><h2>{titulo_g}</h2>
<p class="nota">Cada línea es una apuesta que se hace antes de cada sorteo. Si el azar manda, las líneas oscilan y tienden
a bajar; un patrón real las haría subir sin parar. La escala es logarítmica: cada marca multiplica por 10.</p>
{leyenda(series)}{svg_lineas(series, log=True, umbrales=thr, etiqueta_y='Puntaje E de evidencia')}
<details><summary>Ver como tabla</summary>{tabla(['Serie', 'Fecha', 'E'], filas_t)}</details></section>""")

    # ---------------------------------------------------------------- patrones
    filas = []
    for p in S["top_patrones"][:20]:
        filas.append([e(p["descripcion"]), estado_chip(p["estado"]), n_es(p["premios_prospectivos"]),
                      E_txt(p["log10E_prosp"]) if p["premios_prospectivos"] else "—", n_es(p["premios_evaluados"]),
                      E_txt(p["log10E_total"]),
                      (n_es(p["ventaja_pct_prosp"], 1) + " %") if p["premios_prospectivos"] else "—"])
    out.append(f"""<section><h2>Los 20 patrones con más evidencia</h2>
<p class="nota">Ordenados por su puntaje en datos nuevos. «Ventaja» es cuánto más probable de lo normal le pareció cada
resultado real al patrón, en promedio por premio. De {n_es(m['reglas'] + m['combinadores'])} patrones, hasta
{n_es(m['esperado_cruzar_20_por_azar_max'], 0)} podrían cruzar E = 20 por pura suerte; para declarar uno validado hace
falta E ≥ {n_es(m['umbral_eBH_un_descubrimiento'])}. En el historial ya mirado, {m['cruzaron_20_retro']} patrones están por
encima de 20, una cifra normal para el azar.</p>
{tabla(['Patrón', 'Estado', 'Premios nuevos', 'E nuevos', 'Premios historial', 'E historial', 'Ventaja nuevos'], filas, 'pat')}
<p class="nota">Lista completa: <a href="patrones.csv">patrones.csv</a>.</p></section>""")

    # ---------------------------------------------------------------- aciertos
    serie = S.get("aciertos_serie", [])
    sa = [dict(nombre="Aciertos del top-10 (acumulados)", color="var(--s1)", puntos=[(r["fecha"], r["aciertos"]) for r in serie]),
          dict(nombre="Esperados por azar", color="var(--muted)", punteada=True, puntos=[(r["fecha"], r["esperado"]) for r in serie])]
    rr = S["registro_resumen"]; u1 = S.get("ultima_cifra_top1", {})
    ftab = []
    for k, nom in (("retrospectivo", "Historial ya mirado"), ("prospectivo", "Datos nuevos")):
        if k in ac:
            a = ac[k]; ut = u1.get(k, {})
            ftab.append([nom, n_es(a["premios"]), f"{a['aciertos']}", n_es(a["esperado"], 1),
                         f"{n_es(100 * ut['k'] / ut['n'], 1)} %" if ut.get("n") else "—"])
    ftab.append(["Predicciones guardadas (con huella)", n_es(rr["sorteos"]) + " sorteos", str(rr["aciertos"]), n_es(rr["esperado"], 1), "—"])
    out.append(f"""<section><h2>¿Aciertan los números del combinador?</h2>
<p class="nota">Antes de cada sorteo el combinador elige 10 números por lotería. Si el sorteo es aleatorio, cada seco cae
en esa lista con probabilidad 10 / 10.000; la línea punteada es lo que se espera por suerte. La última cifra más probable
acierta el 10 % de las veces por azar.</p>
{leyenda(sa)}{svg_lineas(sa, marca=(S['inicio_prospectivo'], 'datos nuevos →'), etiqueta_y='Aciertos acumulados')}
{tabla(['Periodo', 'Secos evaluados', 'Aciertos top-10', 'Esperados por azar', 'Acierto última cifra'], ftab)}</section>""")

    # ---------------------------------------------------------------- pre-registro del estudio
    pr = S.get("preregistro")
    if pr and "hipotesis" in pr:
        filas = [[f"<b>{e(h['id'])}</b> {e(h['enunciado'])}<br><span class='tenue'>{e(h['regla'])}"
                  f"{' ' + e(h['nota']) if h.get('nota') else ''}</span>", e(h["progreso"]), e(h["resultado"]),
                  estado_chip(h["veredicto"])] for h in pr["hipotesis"]]
        huella = ("huella SHA-256 verificada: el archivo no ha cambiado desde que se registró" if pr["huella_ok"]
                  else "ATENCIÓN: la huella SHA-256 no coincide; el pre-registro fue modificado")
        out.append(f"""<section><h2>Pre-registro del estudio</h2>
<p class="nota">Cuatro hipótesis fijadas el 17-oct-2026, antes de ver sorteos nuevos, con su regla de decisión
({e(huella)}). El sistema solo las aplica.</p>
{tabla(['Hipótesis', 'Avance', 'Resultado', 'Veredicto'], filas, 'pat')}</section>""")

    # ---------------------------------------------------------------- economía
    filas = []
    for r in S.get("economia", []):
        filas.append([e(r["loteria"]), "$" + n_es(r["precio"]), "$" + n_es(r["ve_neto"]), n_es(r["retorno_neto_pct"], 1) + " %",
                      "$" + n_es(r["perdida"]), n_es(r["multiplicador_necesario"], 2) + "×",
                      (n_es(100 * r["prob_ganar_un_ano"], 2) + " %") if r.get("prob_ganar_un_ano") is not None else "—"])
    if filas:
        out.append(f"""<section><h2>¿Vale la pena comprar?</h2>
<p class="nota">Cálculo exacto del estudio, enumerando todos los billetes posibles, con impuestos (17 % y retención del 20 %
sobre premios mayores a 48 UVT). Para dejar de perder en promedio, un método tendría que multiplicar la probabilidad de
ganar de cada billete por la cifra de la columna «haría falta».</p>
{tabla(['Lotería', 'Billete', 'Le devuelve en promedio', 'Retorno', 'Pierde en promedio', 'Haría falta', 'Gana al cabo de 1 año (1 billete/semana)'], filas)}</section>""")

    # ---------------------------------------------------------------- datos y auditoría
    filas = []
    for c in S["cobertura"]:
        filas.append([e(c["loteria"]), e(c["dia"]), e(fecha_corta(c["ultimo_dato"])) if c["ultimo_dato"] else "—",
                      f'{c["con_secos"]}/{c["sorteos_esperados"]}', n_es(c["secos_independientes"]), n_es(c["excluidos"]),
                      str(c["sorteos_con_cuantia"]), n_es(c["mayores_historial"])])
    falt = S.get("faltantes_recientes", [])
    ftxt = ", ".join(f"{x['loteria']} {fecha_corta(x['fecha_esperada'])}" for x in falt[:30]) or "ninguno"
    desc = S.get("descarga", {})
    dtxt = {"ok": "funcionó", "omitida": "no se ejecutó en esta corrida", "fallo": "falló", "sin conexión": "sin conexión",
            "sin requests": "falta instalar requests"}.get(desc.get("estado"), desc.get("estado", "—"))
    errores = desc.get("errores", [])[:8]
    ing = S["ingesta"]
    rech = ing.get("rechazos", [])
    aud = S.get("auditoria", {})
    clases = d.get("clases", {})
    out.append(f"""<section><h2>Los datos</h2>
<p class="nota">Las listas publicadas de «secos» incluyen premios que no son extracciones independientes (permutaciones
del mayor, mayor ± 1, permutaciones de otro seco). Se guardan, pero se excluyen del análisis: dejarlos crea falsos
patrones. Excluidos hasta hoy: {n_es(d['filas_secos'] - d['secos_independientes'])} de {n_es(d['filas_secos'])} filas.</p>
{tabla(['Lotería', 'Día', 'Último dato', 'Sorteos con secos', 'Secos indep.', 'Excluidos', 'Con cuantía', 'Mayores'], filas)}
<div class="grid2">
<div><h3>Sorteos sin secos (últimas 4 semanas)</h3><p>{e(ftxt)}</p>
<h3>Descarga automática</h3><p>{e(dtxt)}{' · ' + str(desc.get('sorteos_nuevos', 0)) + ' sorteos nuevos' if desc.get('estado') == 'ok' else ''}</p>
{'<ul class="lista">' + ''.join(f'<li>{e(x)}</li>' for x in errores) + '</ul>' if errores else ''}</div>
<div><h3>Última carga manual</h3>
<p>{len(ing.get('archivos', []))} archivo(s) · {ing.get('filas_agregadas', 0)} filas nuevas · {ing.get('cuantias_completadas', 0)} cuantías completadas · {len(rech)} filas rechazadas</p>
{'<ul class="lista">' + ''.join(f'<li>{e(x["archivo"])} fila {e(x["fila"])}: {e(x["motivo"])}</li>' for x in rech[:15]) + '</ul>' if rech else ''}
{'<ul class="lista">' + ''.join(f'<li>{e(x)}</li>' for x in ing.get('avisos', [])[:10]) + '</ul>' if ing.get('avisos') else ''}
<h3>Conflictos entre fuentes</h3><p>{len(S.get('conflictos', []))}</p>
{'<ul class="lista">' + ''.join(f'<li>{e(x)}</li>' for x in S.get('conflictos', [])[:10]) + '</ul>' if S.get('conflictos') else ''}
</div></div>
<details><summary>Clases de filas y eventos de auditoría</summary>
{tabla(['Clase', 'Filas'], [[e(k), n_es(x)] for k, x in clases.items()])}
{tabla(['Evento', 'Veces'], [[e(k), n_es(x)] for k, x in aud.items()])}</details></section>""")

    # ---------------------------------------------------------------- cómo agregar datos y método
    out.append(f"""<section><h2>Cómo agregar resultados</h2>
<ol class="pasos">
<li>Copie <code>data/inbox/plantilla_resultados.csv</code>, llénelo (una fila por premio) y súbalo a la carpeta
<code>data/inbox/</code> del repositorio (en GitHub: <i>Add file → Upload files</i>).</li>
<li>Columnas: <code>loteria, fecha, tipo, numero, serie, cuantia_millones, fuente</code>. «tipo» es <code>mayor</code> o
<code>seco</code>. Escriba los números con sus ceros (<code>0047</code>); si Excel los recorta, el sistema los rellena y avisa.</li>
<li>Al guardar, el sistema se ejecuta solo, incorpora el archivo sin duplicar lo que ya tenía, y actualiza este tablero.
Además descarga cada día los sorteos publicados en internet.</li></ol></section>
<section><h2>Cómo leer este tablero</h2>
<p>Cada patrón es una regla de predicción («los números calientes siguen saliendo», «lo que salió en el mayor anterior
se repite en los secos»…) aplicada a un rasgo del número (cada cifra, las dos últimas, la suma, la estructura) y a un
grupo de sorteos (todas las loterías, cada lotería, los secos de menor cuantía). Los combinadores mezclan, en cada
lotería, las tres reglas que mejor venían funcionando; el azar compite como una regla más.</p>
<p>El puntaje E multiplica, sorteo a sorteo, cuánto más probable le pareció al patrón el resultado real que al azar. Con
sorteos aleatorios E vale 1 en promedio y la probabilidad de que llegue alguna vez a 20 es menor que 1 en 20, sin importar
cuántas veces se revise (desigualdad de Ville). Con {n_es(m['familia_eBH'])} patrones a la vez se usa además e-BH al
{n_es(100 * S['alfa'])} %, que limita la proporción de falsos descubrimientos. El combinador principal (números de los
secos, todas las loterías) se fijó de antemano como prueba única y se valida con E ≥ {n_es(S['umbral_observacion'])}.</p>
<p>Solo cuenta como evidencia lo ocurrido desde el {e(fecha_larga(S['inicio_prospectivo']))}: los datos anteriores ya
se habían analizado en el estudio y servirían para engañarse. Que un patrón se valide no significa que convenga apostar:
tendría además que vencer el margen de la lotería (sección «¿Vale la pena comprar?»).</p></section>
<footer>Datos: LoteríaYa, Telemedellín, Vanguardia, Radio Nacional, resultadosloteriascol.com, bogota.gov.co y cargas
manuales. Código y datos completos en el repositorio. Archivo de estado: <a href="estado.json">estado.json</a>.</footer>""")
    return PLANTILLA.replace("{{CUERPO}}", "\n".join(out) + JS)


PLANTILLA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tablero ATLAS</title>
<meta name="description" content="Seguimiento estadístico de patrones en las loterías colombianas, evaluado en datos nuevos.">
<style>
:root{color-scheme:light;--plane:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;
--base:#c3c2b7;--ring:rgba(11,11,11,.10);--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--ok:#006300;--okbg:#e6f3e6;--obs:#8a5a00;
--obsbg:#fdf3dc;--accent:#2a78d6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--plane:#0d0d0d;--surface:#1a1a19;
--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;--base:#383835;--ring:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;--s3:#199e70;
--ok:#0ca30c;--okbg:#14261a;--obs:#fab219;--obsbg:#2a2312;--accent:#3987e5}}
:root[data-theme="dark"]{color-scheme:dark;--plane:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;
--base:#383835;--ring:rgba(255,255,255,.10);--s1:#3987e5;--s2:#d95926;--s3:#199e70;--ok:#0ca30c;--okbg:#14261a;--obs:#fab219;
--obsbg:#2a2312;--accent:#3987e5}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1040px;margin:0 auto;padding:24px 16px 48px}
header{margin-bottom:20px}.sup{margin:0;color:var(--ink2);font-size:.85rem;letter-spacing:.02em}
h1{font-size:clamp(1.6rem,4vw,2.3rem);line-height:1.15;margin:.2em 0 .3em;text-wrap:balance}
h2{font-size:1.25rem;margin:0 0 .5em}h3{font-size:1rem;margin:1em 0 .3em}
.sub{color:var(--ink2);margin:0}
section{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:20px;margin:16px 0}
.veredicto{border-left:6px solid var(--muted)}.v-senal{border-left-color:var(--ok)}.v-observacion{border-left-color:var(--obs)}
.v-inicio{border-left-color:var(--accent)}.v-et{font-weight:600;color:var(--ink2);font-size:.9rem;margin-bottom:.3em}
.veredicto h2{font-size:1.5rem}.veredicto p{margin:0;color:var(--ink2);max-width:70ch}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;background:none;border:0;padding:0}
.kpi{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:14px 16px}
.kpi-t{color:var(--ink2);font-size:.85rem}.kpi-v{font-size:1.6rem;font-weight:650;font-variant-numeric:tabular-nums;margin:.15em 0}
.kpi-n{color:var(--muted);font-size:.8rem;line-height:1.35}
.nota{color:var(--ink2);max-width:80ch}.tenue{color:var(--muted)}
.aviso{background:var(--obsbg);border-radius:8px;padding:10px 14px;max-width:none}
.graf-env{overflow-x:auto;-webkit-overflow-scrolling:touch}.graf{width:100%;min-width:600px;height:auto;display:block;margin:6px 0}
.graf .grid{stroke:var(--grid);stroke-width:1}.graf .base{stroke:var(--base);stroke-width:1}
.graf .umbral{stroke:var(--muted);stroke-width:1;stroke-dasharray:3 4}
.graf .eje{fill:var(--muted);font-size:13px;font-variant-numeric:tabular-nums}
.graf .hit{fill:transparent;cursor:crosshair}.graf .hit:hover{fill:var(--ring)}
.leyenda{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:.85rem;color:var(--ink2)}
.ley{display:inline-flex;align-items:flex-start;gap:8px}.ley i{display:inline-block;flex:none;width:22px;border-top:2px solid;margin-top:.75em}
.tabla-env{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:8px 0}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th{text-align:left;color:var(--ink2);font-weight:600;border-bottom:1px solid var(--base);padding:6px 8px;white-space:nowrap}
td{border-bottom:1px solid var(--grid);padding:6px 8px;vertical-align:top;font-variant-numeric:tabular-nums}
table.pat td:first-child{min-width:240px}
table.prox .mono{white-space:normal;font-size:.82rem}table.prox td:nth-child(3){min-width:15em}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;letter-spacing:.02em;white-space:nowrap}
.chip{display:inline-block;padding:1px 8px;border-radius:999px;font-size:.78rem;white-space:nowrap;border:1px solid var(--ring);color:var(--ink2)}
.chip.ok{background:var(--okbg);color:var(--ok)}.chip.obs{background:var(--obsbg);color:var(--obs)}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:8px 28px}
.lista{margin:.2em 0;padding-left:1.2em;color:var(--ink2);font-size:.85rem}
details{margin-top:8px}summary{cursor:pointer;color:var(--accent)}
code{font-size:.85em;background:var(--plane);padding:1px 5px;border-radius:4px}
.pasos li{margin:.3em 0}.vacio{color:var(--muted)}
footer{color:var(--muted);font-size:.8rem;margin-top:24px}a{color:var(--accent)}
.sel{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-weight:600;margin:12px 0}
select,input,button{font:inherit;color:var(--ink);background:var(--surface);border:1px solid var(--base);border-radius:8px;padding:8px 10px}
button{cursor:pointer;background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
.sorteo-cab{color:var(--ink2);margin:.4em 0 1em}
.metodos{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}
.met{border:1px solid var(--ring);border-radius:10px;padding:12px 14px;background:var(--plane)}
.met-control{border-style:dashed;border-color:var(--base)}
.met-t{font-weight:650}.met-d{color:var(--ink2);font-size:.82rem;line-height:1.35;margin:.2em 0 .6em}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.num{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:1rem;padding:3px 7px;border-radius:6px;
background:var(--surface);border:1px solid var(--ring);font-variant-numeric:tabular-nums}
.met-r{color:var(--muted);font-size:.78rem;margin-top:.7em}
.consulta{display:flex;gap:8px;flex-wrap:wrap}.consulta input{width:9em;font-family:ui-monospace,Menlo,Consolas,monospace}
.res-num{color:var(--ink2);max-width:80ch;min-height:1.5em}
[hidden]{display:none!important}
</style></head><body><main>
{{CUERPO}}
</main></body></html>"""


def render_md(S: dict) -> str:
    """Resumen en Markdown (state/RESUMEN.md): se lee directamente en GitHub, también en repositorios privados."""
    v = S["veredicto"]; d = S["datos"]; m = S["motor"]; P = S.get("principal", {})
    hay_p = S["premios_prospectivos"] > 0
    col = "log10E_prosp" if hay_p else "log10E_total"
    L = [f"# ATLAS · {v['titulo']}", "",
         f"_Actualizado {fecha_larga(S['generado'])} {S['generado'][11:16]} (Colombia) · último sorteo con datos: "
         f"{fecha_larga(d['ultimo_dato'])}_", "", f"> **{ETIQUETA[v['nivel']]}.** {v['texto']}", "",
         "| Indicador | Valor |", "|---|---|",
         f"| Premios guardados | {n_es(d['secos_independientes'])} secos independientes · {n_es(d['mayores'])} mayores |",
         f"| Seguimiento en datos nuevos | {S['dias_prospectivos']} días · {n_es(S['premios_prospectivos'])} premios |",
         f"| Patrones vigilados | {n_es(m['reglas'] + m['combinadores'])} (validar uno exige E ≥ {n_es(m['umbral_eBH_un_descubrimiento'])}) |",
         f"| Combinador principal | E = {E_txt(P.get(col))} ({'datos nuevos' if hay_p else 'retrospectivo'}; se valida con E ≥ {n_es(S['umbral_observacion'])}) |",
         f"| Validados / en observación | {len(m['validados'])} / {len(m['en_observacion'])} |", "",
         "## Patrones con más evidencia", "", "| Patrón | Estado | E nuevos | E historial |", "|---|---|---|---|"]
    for p in S["top_patrones"][:10]:
        L.append(f"| {p['descripcion']} | {p['estado']} | "
                 f"{E_txt(p['log10E_prosp']) if p['premios_prospectivos'] else '—'} | {E_txt(p['log10E_total'])} |")
    L += ["", "## Números posibles", "",
          "> Ningún método ha demostrado acertar más que el azar: cada número tiene 1 entre 10.000 de salir en cada premio. "
          "La lista «al azar» sirve de comparación.", "",
          "| Método | Aciertos historial | Esperados por azar | Datos nuevos | Guardadas |", "|---|---|---|---|---|"]
    for m in S.get("metodos", []):
        L.append(f"| {m['nombre']} | {m['historial']['aciertos']} | {n_es(m['historial']['esperado'], 1)} | "
                 f"{_marca(m['nuevos'])} | {_marca(m['registrado'])} |")
    nombres = {m["id"]: m["nombre"] for m in S.get("metodos", [])}
    for p in S["proximos"]:
        if p["tipo"] == "seco" and p.get("listas"):
            L += ["", f"**{p['loteria']} · {fecha_larga(p['fecha'])[:-5]}**", ""]
            L += [f"- {nombres.get(k, k)}: `{' '.join(v)}`" for k, v in p["listas"].items() if v]
    ing = S["ingesta"]; desc = S.get("descarga", {})
    L += ["", "## Datos", "",
          f"- Descarga automática: {desc.get('estado', '—')} · sorteos nuevos: {desc.get('sorteos_nuevos', 0)}",
          f"- Última carga manual: {len(ing.get('archivos', []))} archivo(s), {ing.get('filas_agregadas', 0)} filas nuevas, "
          f"{len(ing.get('rechazos', []))} rechazadas",
          f"- Conflictos entre fuentes: {len(S.get('conflictos', []))}"]
    for r in ing.get("rechazos", [])[:10]:
        L.append(f"  - {r['archivo']} fila {r['fila']}: {r['motivo']}")
    falt = S.get("faltantes_recientes", [])
    if falt:
        L.append("- Sorteos sin secos (últimas 4 semanas): " +
                 ", ".join(f"{x['loteria']} {fecha_corta(x['fecha_esperada'])}" for x in falt[:20]))
    L += ["", "El tablero completo está en `site/index.html` (o en GitHub Pages si lo activó)."]
    return "\n".join(L) + "\n"
