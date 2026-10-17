"""Motor de patrones: genera cientos de reglas de predicción, las combina y las califica con e-valores.

Idea en una línea: cada patrón es una apuesta probabilística hecha ANTES de cada sorteo y solo con datos anteriores.
Su puntaje es E = producto de q(resultado) / p0(resultado), donde q es lo que el patrón predijo y p0 lo que da el azar.
  - Si el sorteo es aleatorio, E es una martingala con valor esperado 1: puede subir por suerte, pero la
    probabilidad de que llegue alguna vez a 20 es <= 1/20 (desigualdad de Ville), por mucho que se mire.
  - Si un patrón de verdad anticipa algo, E crece de forma exponencial con los sorteos.
Con ~1.000 patrones vigilados a la vez, varios cruzarán 20 por pura suerte; por eso "validado" exige pasar e-BH
(Wang y Ramdas, 2022), que controla la tasa de falsos descubrimientos entre todos ellos.

Solo cuenta como evidencia lo que ocurre desde INICIO_PROSPECTIVO: antes de esa fecha los datos ya se habían mirado.
"""
from __future__ import annotations

import bisect
import datetime as dt
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import ALFA_FDR, E_OBSERVACION, INICIO_PROSPECTIVO, LOTERIAS, NOMBRE

# ----------------------------------------------------------------------------- rasgos y sus probabilidades exactas
ESTRUCTURAS = ["todas distintas", "un par", "dos pares", "trío", "cuatro iguales"]
P_ESTR = np.array([5040, 4320, 270, 360, 10]) / 1e4
_p = np.ones(10) / 10
P_SUMA = _p
for _ in range(3):
    P_SUMA = np.convolve(P_SUMA, _p)
P_PARES = np.array([1, 4, 6, 4, 1]) / 16
U10, U100 = np.ones(10) / 10, np.ones(100) / 100

RASGOS = {  # nombre: (K, p0, etiqueta)
    "d1": (10, U10, "1.ª cifra"), "d2": (10, U10, "2.ª cifra"), "d3": (10, U10, "3.ª cifra"),
    "d4": (10, U10, "última cifra"), "t2": (100, U100, "dos últimas cifras"),
    "estructura": (5, P_ESTR, "estructura (par, trío…)"), "suma": (37, P_SUMA, "suma de las cifras"),
    "pares": (5, P_PARES, "cuántas cifras pares"),
}
RASGOS_TIPO = {"seco": ["d1", "d2", "d3", "d4", "t2", "estructura", "suma", "pares"],
               "mayor": ["d1", "d2", "d3", "d4", "t2", "estructura", "suma"]}
VENTANA_RECIENTE = {"seco": 28, "mayor": 182}   # días
PESO_AZAR = 0.5                                  # peso previo del azar dentro de cada combinador

ESTRATEGIAS = {
    "caliente": "lo que más ha salido en todo el historial seguirá saliendo más",
    "reciente": "lo que más ha salido en las últimas semanas seguirá saliendo más",
    "fria": "lo que menos ha salido últimamente 'está por salir'",
    "markov": "la última cifra depende de la última cifra del premio mayor anterior",
    "arrastre_mayor": "lo que tuvo el premio mayor anterior de la misma lotería se repite",
    "arrastre_seco": "las terminaciones de los secos del sorteo anterior se repiten",
    "eco": "lo que tuvieron los premios mayores del día anterior (otras loterías) se repite",
}


def rasgos(nums) -> dict[str, np.ndarray]:
    nums = list(nums)
    if not nums:
        return {k: np.zeros(0, int) for k in RASGOS}
    D = np.array([[ord(c) - 48 for c in n] for n in nums], dtype=int)
    srt = np.sort(D, axis=1)
    distintos = 1 + (np.diff(srt, axis=1) != 0).sum(1)
    maxrep = np.array([np.bincount(r, minlength=10).max() for r in D])
    estr = np.select([distintos == 4, distintos == 3, (distintos == 2) & (maxrep == 2), (distintos == 2) & (maxrep == 3)],
                     [0, 1, 2, 3], 4)
    return dict(d1=D[:, 0], d2=D[:, 1], d3=D[:, 2], d4=D[:, 3], t2=D[:, 2] * 10 + D[:, 3], estructura=estr,
                suma=D.sum(1), pares=(D % 2 == 0).sum(1))


def _conteo(v, K):
    return np.bincount(v, minlength=K).astype(float) if len(v) else np.zeros(K)


# ----------------------------------------------------------------------------- estrategias
def q_suavizada(c, n, p0, K):
    A = max(200.0, 20.0 * K)
    return (c + A * p0) / (n + A)


def q_fria(c, n, p0):
    if n <= 0:
        return p0
    z = np.clip((c - n * p0) / np.sqrt(n * p0 * (1 - p0)), -3, 3)
    q = p0 * np.exp(-0.3 * z)
    return q / q.sum()


def q_conjunto(valores, p0):
    v = np.unique(np.asarray(valores, int))
    if len(v) == 0:
        return p0
    u = np.zeros_like(p0); u[v] = 1.0 / len(v)
    return 0.9 * p0 + 0.1 * u


class Contador:
    """Conteos acumulados por fecha, con consulta de ventana reciente."""

    def __init__(self, K):
        self.cum = np.zeros(K); self.fechas: list[int] = []; self.hist: list[np.ndarray] = []

    def agregar(self, ford, vec):
        self.cum = self.cum + vec; self.fechas.append(ford); self.hist.append(self.cum.copy())

    def reciente(self, ford, W):
        i = bisect.bisect_right(self.fechas, ford - W)
        return self.cum - (self.hist[i - 1] if i > 0 else 0)


@dataclass
class Patron:
    id: str; tipo: str; alcance: str; rasgo: str; estrategia: str
    logE: float = 0.0; n: int = 0; logE_p: float = 0.0; n_p: int = 0; max_logE_p: float = 0.0
    por_lot: dict = field(default_factory=dict)        # logE acumulado en cada lotería (para el combinador)
    tray: list = field(default_factory=list)            # (fecha, logE_total) al cierre de cada fecha con datos

    def nombre_alcance(self):
        return {"todas": "todas las loterías", "menor": "menor cuantía"}.get(self.alcance,
                                                                                    NOMBRE.get(self.alcance, self.alcance))

    def descripcion(self):
        t = "secos" if self.tipo == "seco" else "premios mayores"
        return f"{RASGOS[self.rasgo][2].capitalize()} de los {t} ({self.nombre_alcance()}): {ESTRATEGIAS[self.estrategia]}"


def _catalogo(tipo, alcances):
    pats = []
    for a in alcances:
        for r in RASGOS_TIPO[tipo]:
            for e in ("caliente", "reciente", "fria"):
                pats.append(Patron(f"{tipo}|{a}|{r}|{e}", tipo, a, r, e))
        pats.append(Patron(f"{tipo}|{a}|d4|markov", tipo, a, "d4", "markov"))
        for r in ("d4", "t2"):
            pats.append(Patron(f"{tipo}|{a}|{r}|arrastre_mayor", tipo, a, r, "arrastre_mayor"))
        if tipo == "seco":
            pats.append(Patron(f"{tipo}|{a}|t2|arrastre_seco", tipo, a, "t2", "arrastre_seco"))
        else:
            for r in ("d4", "t2"):
                pats.append(Patron(f"{tipo}|{a}|{r}|eco", tipo, a, r, "eco"))
    return pats


# ----------------------------------------------------------------------------- motor
class Motor:
    def __init__(self, mayores: pd.DataFrame, secos: pd.DataFrame, inicio_prospectivo: str = INICIO_PROSPECTIVO,
                 top_k: int = 10):
        self.ini_p = inicio_prospectivo; self.top_k = top_k
        may = mayores[mayores.numero.astype(str).str.fullmatch(r"\d{4}")].copy()
        sec = secos[secos.clase == "seco"].copy() if "clase" in secos else secos.copy()
        self.lots = sorted(set(may.slug) | set(sec.slug))
        self.draws = {"mayor": self._sorteos(may, "mayor"), "seco": self._sorteos(sec, "seco")}
        self.pats: dict[str, Patron] = {}
        for tipo, alc in (("seco", ["todas"] + self.lots + ["menor"]), ("mayor", ["todas"] + self.lots)):
            for p in _catalogo(tipo, alc):
                self.pats[p.id] = p
        self.cont = {}          # (tipo, alcance, rasgo) -> Contador
        self.markov = {}        # (tipo, alcance) -> matriz 10x10
        self.prev = {}          # (tipo, slug) -> rasgos del sorteo anterior
        self.prev_mayor = {}    # slug -> rasgos del mayor anterior
        self.eco_mayor = None   # rasgos de los mayores de la fecha anterior con mayores
        comb_ids = [(t, l, r) for t in ("seco", "mayor") for l in self.lots for r in RASGOS_TIPO[t] + ["numero"]]
        # tray: [(fecha, log E de la mezcla al cierre de la fecha)]; n y n_p: premios evaluados
        self.comb = {k: dict(n=0, n_p=0, tray=[]) for k in comb_ids}
        self.aciertos = []      # una fila por sorteo: aciertos del top-k del combinador de números
        self.d4_top1 = []

    # -------------------------------------------------------------------------
    @staticmethod
    def _sorteos(df, tipo):
        out = []
        if df.empty:
            return out
        df = df.sort_values(["fecha", "slug"] + (["fila"] if "fila" in df else []))
        for (fecha, slug), g in df.groupby(["fecha", "slug"], sort=True):
            menor = g.menor_cuantia.fillna(False).astype(bool).values if "menor_cuantia" in g else np.zeros(len(g), bool)
            out.append(dict(fecha=fecha, ford=dt.date.fromisoformat(fecha).toordinal(), slug=slug,
                            nums=g.numero.tolist(), r=rasgos(g.numero), menor=menor))
        return out

    def _c(self, tipo, alc, r):
        k = (tipo, alc, r)
        if k not in self.cont:
            self.cont[k] = Contador(RASGOS[r][0])
        return self.cont[k]

    def _mk(self, tipo, alc):
        return self.markov.setdefault((tipo, alc), np.zeros((10, 10)))

    def q(self, p: Patron, slug: str, ford: int) -> np.ndarray:
        K, p0, _ = RASGOS[p.rasgo]
        alc = p.alcance
        if p.estrategia in ("caliente", "reciente", "fria"):
            c = self._c(p.tipo, alc, p.rasgo)
            if p.estrategia == "caliente":
                return q_suavizada(c.cum, c.cum.sum(), p0, K)
            v = c.reciente(ford, VENTANA_RECIENTE[p.tipo])
            return q_suavizada(v, v.sum(), p0, K) if p.estrategia == "reciente" else q_fria(v, v.sum(), p0)
        if p.estrategia == "markov":
            pm = self.prev_mayor.get(slug)
            if pm is None:
                return p0
            row = self._mk(p.tipo, alc)[pm["d4"][0]]
            return (row + 20.0) / (row.sum() + 200.0)
        if p.estrategia == "arrastre_mayor":
            pm = self.prev_mayor.get(slug)
            return p0 if pm is None else q_conjunto(pm[p.rasgo], p0)
        if p.estrategia == "arrastre_seco":
            pr = self.prev.get(("seco", slug))
            return p0 if pr is None else q_conjunto(pr[p.rasgo], p0)
        if p.estrategia == "eco":
            return p0 if self.eco_mayor is None else q_conjunto(self.eco_mayor[p.rasgo], p0)
        raise ValueError(p.estrategia)

    def candidatos(self, tipo, slug, rasgo):
        return [p for p in (self.pats.get(f"{tipo}|todas|{rasgo}|{e}") for e in ESTRATEGIAS) if p] + \
               [p for p in (self.pats.get(f"{tipo}|{slug}|{rasgo}|{e}") for e in ESTRATEGIAS) if p]

    def _pesos(self, tipo, slug, rasgo):
        """Mezcla bayesiana: el azar con peso previo 1/2 y el resto repartido entre las reglas candidatas.
        Peso actual de cada regla = peso previo x su E en esta lotería. El E de la mezcla es la suma de esos productos,
        así que nunca baja de 1/2 por culpa de reglas malas, y crece si alguna regla de verdad anticipa algo."""
        cands = self.candidatos(tipo, slug, rasgo)
        lp = [math.log(PESO_AZAR)] + [math.log((1 - PESO_AZAR) / len(cands))] * len(cands)
        sc = [0.0] + [p.por_lot.get(slug, 0.0) if p.alcance == "todas" else p.logE for p in cands]
        lw = np.array(lp) + np.array(sc)
        mx = lw.max(); logE = float(mx + np.log(np.exp(lw - mx).sum()))
        return ["azar"] + [p.id for p in cands], cands, np.exp(lw - logE), logE

    def mezcla(self, tipo, slug, rasgo, ford, qcache):
        ids, cands, w, _ = self._pesos(tipo, slug, rasgo)
        qs = [RASGOS[rasgo][1]]
        for p in cands:
            qq = qcache.get(p.id)
            if qq is None:
                qq = qcache[p.id] = self.q(p, slug, ford)
            qs.append(qq)
        q = (w[:, None] * np.array(qs)).sum(0)
        top = np.argsort(-w)[:3]
        return q / q.sum(), [(ids[i], round(float(w[i]), 3)) for i in top]

    def top_numeros(self, qs):
        P = np.multiply.outer(np.multiply.outer(np.multiply.outer(qs[0], qs[1]), qs[2]), qs[3]).ravel()
        idx = np.argpartition(-P, self.top_k)[:self.top_k]
        idx = idx[np.argsort(-P[idx])]
        return [f"{i:04d}" for i in idx], P[idx]

    # -------------------------------------------------------------------------
    def correr(self):
        fechas = sorted({d["fecha"] for t in self.draws for d in self.draws[t]})
        por_fecha = {t: {} for t in self.draws}
        for t, L in self.draws.items():
            for d in L:
                por_fecha[t].setdefault(d["fecha"], []).append(d)
        for fecha in fechas:
            ford = dt.date.fromisoformat(fecha).toordinal()
            prosp = fecha >= self.ini_p
            incr = {}       # id -> (dlogE, n, slug)
            tocados = set()
            for tipo in ("mayor", "seco"):
                for d in por_fecha[tipo].get(fecha, []):
                    slug = d["slug"]; qcache = {}
                    for alc in ("todas", slug, "menor") if tipo == "seco" else ("todas", slug):
                        mask = d["menor"] if alc == "menor" else None
                        if mask is not None and not mask.any():
                            continue
                        for r in RASGOS_TIPO[tipo]:
                            v = d["r"][r] if mask is None else d["r"][r][mask]
                            if not len(v):
                                continue
                            for e in ESTRATEGIAS:
                                p = self.pats.get(f"{tipo}|{alc}|{r}|{e}")
                                if p is None:
                                    continue
                                qq = self.q(p, slug, ford)
                                if alc != "menor":
                                    qcache[p.id] = qq
                                dl = float(np.log(qq[v] / RASGOS[r][1][v]).sum())
                                incr.setdefault(p.id, []).append((dl, len(v), slug))
                    # combinadores de esta lotería
                    qs = {}
                    for r in ("d1", "d2", "d3", "d4"):
                        qs[r], _ = self.mezcla(tipo, slug, r, ford, qcache)
                    for r in RASGOS_TIPO[tipo] + ["numero"]:
                        c = self.comb[(tipo, slug, r)]; c["n"] += len(d["nums"]); c["n_p"] += len(d["nums"]) * prosp
                    tocados.add((tipo, slug))
                    top, _ = self.top_numeros([qs[r] for r in ("d1", "d2", "d3", "d4")])
                    st = set(top)
                    hits = [n for n in d["nums"] if n in st]
                    self.aciertos.append(dict(fecha=fecha, slug=slug, tipo=tipo, premios=len(d["nums"]),
                                              aciertos=len(hits), esperado=len(d["nums"]) * self.top_k / 1e4,
                                              numeros_acertados=" ".join(hits), prospectivo=prosp))
                    best = int(np.argmax(qs["d4"]))
                    self.d4_top1.append(dict(fecha=fecha, slug=slug, tipo=tipo, n=len(d["nums"]),
                                             k=int((d["r"]["d4"] == best).sum()), prospectivo=prosp))
            # actualizar puntajes (después de predecir todo lo de la fecha)
            for pid, lst in incr.items():
                p = self.pats[pid]
                for dl, n, slug in lst:
                    p.logE += dl; p.n += n
                    if p.alcance == "todas":
                        p.por_lot[slug] = p.por_lot.get(slug, 0.0) + dl
                    if prosp:
                        p.logE_p += dl; p.n_p += n; p.max_logE_p = max(p.max_logE_p, p.logE_p)
                p.tray.append((fecha, p.logE, p.logE_p))
            # actualizar conteos y memoria de sorteos anteriores (secos primero: su Markov se entrena con el
            # mayor ANTERIOR, igual que cuando predice)
            for tipo in ("seco", "mayor"):
                ds = por_fecha[tipo].get(fecha, [])
                if not ds:
                    continue
                agg = {}
                for d in ds:
                    slug = d["slug"]
                    for alc in ("todas", slug, "menor") if tipo == "seco" else ("todas", slug):
                        mask = d["menor"] if alc == "menor" else None
                        if mask is not None and not mask.any():
                            continue
                        for r in RASGOS_TIPO[tipo]:
                            v = d["r"][r] if mask is None else d["r"][r][mask]
                            agg[(alc, r)] = agg.get((alc, r), 0) + _conteo(v, RASGOS[r][0])
                        pm = self.prev_mayor.get(slug)
                        if pm is not None:
                            v4 = d["r"]["d4"] if mask is None else d["r"]["d4"][mask]
                            np.add.at(self._mk(tipo, alc), (pm["d4"][0], v4), 1)
                for (alc, r), vec in agg.items():
                    self._c(tipo, alc, r).agregar(ford, vec)
                for d in ds:
                    self.prev[(tipo, d["slug"])] = d["r"]
                if tipo == "mayor":
                    for d in ds:
                        self.prev_mayor[d["slug"]] = d["r"]
                    self.eco_mayor = rasgos([n for d in ds for n in d["nums"]])
            # E de cada combinador tocado hoy (con los puntajes ya actualizados)
            for tipo, slug in tocados:
                num = 0.0
                for r in RASGOS_TIPO[tipo]:
                    lE = self._pesos(tipo, slug, r)[3]
                    self.comb[(tipo, slug, r)]["tray"].append((fecha, lE))
                    num += lE if r in ("d1", "d2", "d3", "d4") else 0.0
                self.comb[(tipo, slug, "numero")]["tray"].append((fecha, num))
        return self

    # ------------------------------------------------------------------------- predicción de los próximos sorteos
    def predecir(self, tipo, slug, fecha):
        ford = dt.date.fromisoformat(fecha).toordinal(); qcache = {}; qs = {}; usados = {}
        for r in ("d1", "d2", "d3", "d4", "t2"):
            qs[r], usados[r] = self.mezcla(tipo, slug, r, ford, qcache)
        top, probs = self.top_numeros([qs[r] for r in ("d1", "d2", "d3", "d4")])
        t2 = np.argsort(-qs["t2"])[:5]
        return dict(loteria=NOMBRE.get(slug, slug), slug=slug, fecha=fecha, tipo=tipo,
                    top_numeros=top, prob_top_numeros=[round(float(x), 7) for x in probs],
                    ultima_cifra=[dict(cifra=int(i), prob=round(float(qs["d4"][i]), 4)) for i in np.argsort(-qs["d4"])[:3]],
                    terminaciones=[dict(t2=f"{i:02d}", prob=round(float(qs["t2"][i]), 4)) for i in t2],
                    reglas_usadas={r: [dict(regla=i, peso=w) for i, w in usados[r]] for r in usados})


# ----------------------------------------------------------------------------- e-BH y tablas de salida
def ebh(E: np.ndarray, alfa: float) -> np.ndarray:
    """e-BH (Wang y Ramdas 2022): rechaza los k mayores, con k = máx{k : E_(k) >= m / (alfa k)}."""
    m = len(E)
    if m == 0:
        return np.zeros(0, bool)
    o = np.argsort(-E); k = 0
    for i in range(m):
        if E[o[i]] >= m / (alfa * (i + 1)):
            k = i + 1
    rej = np.zeros(m, bool); rej[o[:k]] = True
    return rej


def tablas(M: Motor) -> dict:
    L10 = 1 / math.log(10)
    filas = []
    for p in M.pats.values():
        filas.append(dict(id=p.id, clase="regla", tipo=p.tipo, alcance=p.nombre_alcance(), rasgo=RASGOS[p.rasgo][2],
                          estrategia=p.estrategia, descripcion=p.descripcion(), premios_evaluados=p.n,
                          log10E_total=p.logE * L10, premios_prospectivos=p.n_p, log10E_prosp=p.logE_p * L10,
                          max_log10E_prosp=p.max_logE_p * L10,
                          ventaja_pct_total=100 * (math.exp(p.logE / p.n) - 1) if p.n else 0.0,
                          ventaja_pct_prosp=100 * (math.exp(p.logE_p / p.n_p) - 1) if p.n_p else 0.0))
    for (tipo, slug, r), c in M.comb.items():
        if c["n"] == 0:
            continue
        sr = serie_comb(M, tipo, slug, r)
        et = "número completo" if r == "numero" else RASGOS[r][2]
        t = "secos" if tipo == "seco" else "premios mayores"
        filas.append(_fila_comb(f"comb|{tipo}|{slug}|{r}", tipo, NOMBRE.get(slug, slug), et, sr, c["n"], c["n_p"],
                                f"Combinador: {et} de los {t} de {NOMBRE.get(slug, slug)}, mezclando todas las reglas "
                                "según cómo les ha ido en esa lotería (el azar pesa la mitad al comienzo)"))
    # combinador global: promedio de los combinadores de cada lotería (sigue siendo un e-proceso válido)
    for tipo in ("seco", "mayor"):
        for r in RASGOS_TIPO[tipo] + ["numero"]:
            cs = [c for (t, s_, rr), c in M.comb.items() if t == tipo and rr == r and c["n"]]
            if not cs:
                continue
            sr = serie_comb(M, tipo, "todas", r)
            et = "número completo" if r == "numero" else RASGOS[r][2]
            filas.append(_fila_comb(f"comb|{tipo}|todas|{r}", tipo, "todas las loterías", et, sr,
                                    sum(c["n"] for c in cs), sum(c["n_p"] for c in cs),
                                    f"Combinador global: {et} de los {'secos' if tipo == 'seco' else 'premios mayores'}, "
                                    "promedio de los combinadores de cada lotería"))
    T = pd.DataFrame(filas)
    principal = "comb|seco|todas|numero"
    fam = T[T.id != principal]
    rej = ebh(10 ** fam.log10E_prosp.values, ALFA_FDR)
    T["validado_eBH"] = False
    T.loc[fam.index[rej], "validado_eBH"] = True
    e_pr = 10 ** T.log10E_prosp
    T["estado"] = np.select(
        [T.premios_prospectivos == 0, T.validado_eBH, (T.id == principal) & (e_pr >= E_OBSERVACION),
         e_pr >= E_OBSERVACION],
        ["sin datos nuevos", "validado", "validado (prueba principal)", "en observación"],
        "sin evidencia")
    T = T.sort_values(["log10E_prosp", "log10E_total"], ascending=False).reset_index(drop=True)
    m = len(fam)
    resumen = dict(
        reglas=int((T.clase == "regla").sum()), combinadores=int((T.clase == "combinador").sum()), familia_eBH=m,
        umbral_eBH_un_descubrimiento=m / ALFA_FDR, alfa=ALFA_FDR, e_observacion=E_OBSERVACION,
        validados=T[T.estado.str.startswith("validado")].id.tolist(),
        en_observacion=T[T.estado == "en observación"].id.tolist(),
        cruzaron_20_retro=int((T.log10E_total >= math.log10(20)).sum()),
        esperado_cruzar_20_por_azar_max=round(0.05 * len(T), 1),
        principal=principal,
    )
    ac = pd.DataFrame(M.aciertos)
    d4 = pd.DataFrame(M.d4_top1)
    return dict(patrones=T, aciertos=ac, d4_top1=d4, resumen=resumen)


def _fila_comb(id_, tipo, alcance, et, sr, n, n_p, desc):
    L10 = 1 / math.log(10)
    lE = sr[-1][1] if sr else 0.0; lp = sr[-1][2] if sr else 0.0
    mx = max([b for f, a, b in sr] + [0.0])
    return dict(id=id_, clase="combinador", tipo=tipo, alcance=alcance, rasgo=et, estrategia="combinador",
                descripcion=desc, premios_evaluados=n, log10E_total=lE * L10, premios_prospectivos=n_p,
                log10E_prosp=lp * L10, max_log10E_prosp=mx * L10,
                ventaja_pct_total=100 * (math.exp(lE / n) - 1) if n else 0.0,
                ventaja_pct_prosp=100 * (math.exp(lp / n_p) - 1) if n_p else 0.0)


def serie_comb(M: Motor, tipo: str, slug: str, r: str) -> list[tuple[str, float, float]]:
    """[(fecha, log E total, log E desde el inicio prospectivo)] de un combinador (o del global si slug='todas')."""
    if slug != "todas":
        tr = M.comb.get((tipo, slug, r), {}).get("tray", [])
        base = 0.0
        out = []
        for f, lE in tr:
            if f < M.ini_p:
                base = lE
            out.append((f, lE, lE - base if f >= M.ini_p else 0.0))
        return out
    lots = [s for (t, s, rr), c in M.comb.items() if t == tipo and rr == r and c["n"]]
    if not lots:
        return []
    ev = sorted((f, s, lE) for s in lots for f, lE in M.comb[(tipo, s, r)]["tray"])
    last = {s: 0.0 for s in lots}; out = []; base = 0.0; i = 0
    while i < len(ev):
        f = ev[i][0]
        while i < len(ev) and ev[i][0] == f:
            last[ev[i][1]] = ev[i][2]; i += 1
        v = np.array(list(last.values())); mx = v.max()
        lE = float(mx + np.log(np.exp(v - mx).sum()) - np.log(len(v)))
        if f < M.ini_p:
            base = lE
        out.append((f, lE, lE - base if f >= M.ini_p else 0.0))
    return out


def trayectorias(M: Motor, ids: list[str]) -> pd.DataFrame:
    L10 = 1 / math.log(10); out = []
    for i in ids:
        if i in M.pats:
            tr = M.pats[i].tray
        elif i.startswith("comb|"):
            _, tipo, slug, r = i.split("|")
            tr = serie_comb(M, tipo, slug, r)
        else:
            continue
        out += [dict(id=i, fecha=f, log10E_total=a * L10, log10E_prosp=b * L10) for f, a, b in tr]
    return pd.DataFrame(out, columns=["id", "fecha", "log10E_total", "log10E_prosp"])
