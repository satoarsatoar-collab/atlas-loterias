"""
PROYECTO ATLAS - Paso 1: construcción y auditoría del dataset.

Entradas (data/raw):
  hist_<slug>.csv            premios mayores (LoteríaYa, página /historial)
  ly/<slug>_<fecha>.txt      secos por sorteo (LoteríaYa, página /resultado/<fecha>)
  labeled/<fuente>_<slug>_<fecha>.csv   secos con cuantía (Telemedellín, Vanguardia,
                             Radio Nacional, resultadosloteriascol.com)
Salidas (data/processed):
  mayores.csv, secos.csv, audit_log.csv, inventory.csv, label_crosscheck.csv

Regla de oro: los números y series se tratan SIEMPRE como texto (0047 != 47).
"""
import os, glob, re, json
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed")
os.makedirs(OUT, exist_ok=True)

NAMES = {
    "loteria-de-bogota": "Bogotá", "loteria-de-boyaca": "Boyacá",
    "loteria-de-cundinamarca": "Cundinamarca", "loteria-de-la-cruz-roja": "Cruz Roja",
    "loteria-de-manizales": "Manizales", "loteria-de-medellin": "Medellín",
    "loteria-de-risaralda": "Risaralda", "loteria-de-santander": "Santander",
    "loteria-del-cauca": "Cauca", "loteria-del-huila": "Huila", "loteria-del-meta": "Meta",
    "loteria-del-quindio": "Quindío", "loteria-del-tolima": "Tolima", "loteria-del-valle": "Valle",
}
WEEKDAY = {  # día oficial de juego
    "loteria-de-cundinamarca": 0, "loteria-del-tolima": 0, "loteria-de-la-cruz-roja": 1,
    "loteria-del-huila": 1, "loteria-de-manizales": 2, "loteria-del-meta": 2,
    "loteria-del-valle": 2, "loteria-de-bogota": 3, "loteria-del-quindio": 3,
    "loteria-de-medellin": 4, "loteria-de-risaralda": 4, "loteria-de-santander": 4,
    "loteria-de-boyaca": 5, "loteria-del-cauca": 5,
}
WIN_START, WIN_END = "2026-08-17", "2026-10-17"
LY = "https://www.loteriaya.com.co/loteria/{slug}/resultado/{date}"

audit = []
def log(kind, slug, date, detail):
    audit.append({"tipo": kind, "loteria": NAMES.get(slug, slug), "fecha": date, "detalle": detail})

def is4(x): return isinstance(x, str) and re.fullmatch(r"\d{4}", x) is not None
def is3(x): return isinstance(x, str) and re.fullmatch(r"\d{3}", x) is not None

# ------------------------------------------------------------------ mayores
rows = []
for f in sorted(glob.glob(os.path.join(RAW, "hist_*.csv"))):
    slug = os.path.basename(f)[5:-4]
    d = pd.read_csv(f, dtype=str, keep_default_na=False)
    for _, r in d.iterrows():
        if r.sorteo == "NODRAW":
            log("sin_sorteo", slug, r.date, "La fuente marca la fecha como 'sin sorteo'")
            continue
        rows.append(dict(slug=slug, loteria=NAMES[slug], fecha=r.date, sorteo=r.sorteo,
                         numero=r.number, serie=r.series, fuente="LoteríaYa /historial",
                         url=f"https://www.loteriaya.com.co/loteria/{slug}/historial"))
may = pd.DataFrame(rows)

# añadir mayores del período que el historial aún no tenía (tomados de la página del sorteo)
for f in sorted(glob.glob(os.path.join(RAW, "ly", "*.txt"))):
    key = os.path.basename(f)[:-4]
    slug, date = key.rsplit("_", 1)
    h = open(f).read().strip().split("\n")[0].split(",")
    _, sorteo, num, ser = h
    m = (may.slug == slug) & (may.fecha == date)
    if not m.any():
        may = pd.concat([may, pd.DataFrame([dict(slug=slug, loteria=NAMES[slug], fecha=date, sorteo=sorteo,
              numero=num, serie=ser, fuente="LoteríaYa /resultado", url=LY.format(slug=slug, date=date))])])
    else:
        old = may.loc[m].iloc[0]
        if (old.numero, old.serie) != (num, ser):
            log("discrepancia_mayor", slug, date, f"historial {old.numero}/{old.serie} vs página {num}/{ser}")

may["estado"] = "ok"
for i, r in may.iterrows():
    probs = []
    if not is4(r.numero): probs.append("numero_invalido")
    if not is3(r.serie): probs.append("serie_faltante")
    wd = pd.Timestamp(r.fecha).weekday()
    if wd != WEEKDAY[r.slug]: probs.append(f"dia_atipico({['lun','mar','mié','jue','vie','sáb','dom'][wd]})")
    if probs:
        may.at[i, "estado"] = ";".join(probs)
        log("mayor_" + probs[0].split("(")[0], r.slug, r.fecha, f"{r.numero}/{r.serie} sorteo {r.sorteo}: {';'.join(probs)}")
# sorteos duplicados o con salto en la numeración
for slug, g in may.sort_values("fecha").groupby("slug"):
    s = pd.to_numeric(g.sorteo, errors="coerce")
    dup = g[s.duplicated(keep=False) & s.notna()]
    for _, r in dup.iterrows():
        log("sorteo_duplicado", slug, r.fecha, f"número de sorteo {r.sorteo} repetido")
    diffs = s.diff()
    for (_, r), dlt in zip(g.iterrows(), diffs):
        if pd.notna(dlt) and dlt not in (1, 0):
            log("salto_numeracion", slug, r.fecha, f"sorteo {r.sorteo}: salto de {int(dlt)} respecto al anterior")
may = may.sort_values(["fecha", "slug"]).reset_index(drop=True)
may["en_ventana"] = (may.fecha >= WIN_START) & (may.fecha <= WIN_END)
may.to_csv(os.path.join(OUT, "mayores.csv"), index=False)

# ------------------------------------------------------------------ secos
def digits_key(n): return "".join(sorted(n))

srows = []
for f in sorted(glob.glob(os.path.join(RAW, "ly", "*.txt"))):
    key = os.path.basename(f)[:-4]
    slug, date = key.rsplit("_", 1)
    lines = [l.strip() for l in open(f).read().strip().split("\n") if l.strip()]
    _, sorteo, M, Ms = lines[0].split(",")
    body = lines[1:]
    if not body:
        log("sorteo_sin_secos", slug, date, "La página del sorteo no publica tabla de secos")
        continue
    seen_groups = {}      # (serie, multiset) -> primera fila que lo originó
    seen_exact = {}
    for idx, l in enumerate(body, 1):
        parts = l.split(",")
        num = parts[0]; ser = parts[1] if len(parts) > 1 else ""
        clase, nota = "seco", ""
        if not is4(num):
            clase, nota = "invalido", "número mal formado"
        elif not is3(ser):
            clase, nota = "serie_faltante", "fila sin serie"
        elif ser == Ms and digits_key(num) == digits_key(M) and num != M:
            clase, nota = "derivado_permutacion_mayor", f"permutación del mayor {M} con su serie"
        elif ser == Ms and is4(M) and min((int(num) - int(M)) % 10000, (int(M) - int(num)) % 10000) == 1:
            clase, nota = "derivado_mayor_pm1", f"mayor {M} ±1 con su serie"
        elif (ser, digits_key(num)) in seen_groups and seen_groups[(ser, digits_key(num))] != num:
            clase, nota = "derivado_permutacion_seco", f"permutación del seco {seen_groups[(ser, digits_key(num))]} con la misma serie"
        elif (num, ser) in seen_exact:
            clase, nota = "duplicado_en_sorteo", f"repite la fila {seen_exact[(num, ser)]}"
        elif ser == "000":
            clase, nota = "serie_000_ambigua", "serie 000: en otras fuentes no figura como seco (ver auditoría)"
        if clase in ("seco", "serie_000_ambigua"):
            seen_groups.setdefault((ser, digits_key(num)), num)
        seen_exact.setdefault((num, ser), idx)
        srows.append(dict(slug=slug, loteria=NAMES[slug], fecha=date, sorteo=sorteo, mayor=M, serie_mayor=Ms,
                          fila=idx, numero=num, serie=ser, clase=clase, nota=nota,
                          fuente="LoteríaYa", url=LY.format(slug=slug, date=date)))
sec = pd.DataFrame(srows)

# ------------------------------------------------------------------ cuantías (segunda fuente)
lab_rows = []
for f in sorted(glob.glob(os.path.join(RAW, "labeled", "*.csv"))):
    b = os.path.basename(f)[:-4]
    partial = b.endswith("_PARTIAL")
    b = b.replace("_PARTIAL", "")
    src, rest = b.split("_", 1)
    slug, date = rest.rsplit("_", 1)
    d = pd.read_csv(f, dtype=str)
    d["slug"], d["fecha"], d["fuente_cuantia"], d["parcial"] = slug, date, src, partial
    lab_rows.append(d)
lab = pd.concat(lab_rows)
lab["amount_millions"] = lab.amount_millions.astype(int)

# Reconciliación documentada: Telemedellín 25-sep lista 8 secos de $100M y ninguno de $1.000M.
# El plan oficial (y las otras 7 fechas) tiene 2 de $1.000M y 6 de $100M; las dos primeras filas
# de la página ocupan la posición de los de $1.000M. Se corrigen y se deja constancia.
m = (lab.slug == "loteria-de-medellin") & (lab.fecha == "2026-09-25") & lab.number.isin(["0840", "8629"])
lab.loc[m, "amount_millions"] = 1000
log("cuantia_corregida", "loteria-de-medellin", "2026-09-25",
    "Telemedellín rotula 0840/259 y 8629/177 como $100M; el plan exige 2 secos de $1.000M: se reasignan")

cc = []
for (slug, date), g in lab.groupby(["slug", "fecha"]):
    s = sec[(sec.slug == slug) & (sec.fecha == date)]
    A = set(zip(s.numero, s.serie)); B = set(zip(g.number, g.series))
    only_ly = sorted(A - B); only_lab = sorted(B - A)
    cc.append(dict(loteria=NAMES[slug], fecha=date, fuente=g.fuente_cuantia.iloc[0], parcial=g.parcial.iloc[0],
                   filas_ly=len(A), filas_fuente2=len(B), coinciden=len(A & B),
                   solo_ly=";".join("/".join(x) for x in only_ly), solo_fuente2=";".join("/".join(x) for x in only_lab)))
    for x in only_lab:
        log("discrepancia_fuentes", slug, date, f"{x[0]}/{x[1]} aparece en {g.fuente_cuantia.iloc[0]} y no en LoteríaYa")
cc = pd.DataFrame(cc)
cc.to_csv(os.path.join(OUT, "label_crosscheck.csv"), index=False)

lab_key = lab.set_index(["slug", "fecha", "number", "series"])[["amount_millions", "fuente_cuantia"]]
lab_key = lab_key[~lab_key.index.duplicated()]
sec = sec.join(lab_key, on=["slug", "fecha", "numero", "serie"])
labeled_draws = set(zip(lab.slug, lab.fecha))
sec["sorteo_con_cuantia"] = [(a, b) in labeled_draws for a, b in zip(sec.slug, sec.fecha)]
sec["verificacion"] = np.where(sec.amount_millions.notna(), "dos fuentes", "una fuente (LoteríaYa)")
# en sorteos con cuantía, filas 'seco' que la segunda fuente no reconoce
odd = sec.sorteo_con_cuantia & sec.amount_millions.isna() & (sec.clase == "seco")
for _, r in sec[odd].iterrows():
    log("seco_sin_confirmar", r.slug, r.fecha, f"{r.numero}/{r.serie} no figura en la fuente con cuantías")

# rango de cuantía dentro de cada lotería (1 = la más baja)
tiers = lab.groupby("slug").amount_millions.apply(lambda x: sorted(set(x)))
def tier(r):
    if pd.isna(r.amount_millions): return np.nan
    return tiers[r.slug].index(int(r.amount_millions)) + 1
sec["rango_cuantia"] = sec.apply(tier, axis=1)
# Bogotá se incorporó DESPUÉS de formular las hipótesis de cuantía: es un conjunto de replicación independiente.
REPLICACION = {"loteria-de-bogota"}
sec["conjunto_cuantia"] = np.where(sec.amount_millions.isna(), "", np.where(sec.slug.isin(REPLICACION), "replicación", "formulación"))
sec["menor_cuantia"] = sec.rango_cuantia == 1
sec["en_ventana"] = True
sec.to_csv(os.path.join(OUT, "secos.csv"), index=False)

# ------------------------------------------------------------------ inventario
wd = pd.read_csv(os.path.join(RAW, "window_draws.csv"))
inv = []
for slug in NAMES:
    exp = wd[wd.slug == slug]
    s = sec[sec.slug == slug]
    with_secos = s.fecha.nunique()
    inv.append(dict(
        loteria=NAMES[slug], dia=["lun", "mar", "mié", "jue", "vie", "sáb"][WEEKDAY[slug]],
        sorteos_en_ventana=len(exp),
        mayores_obtenidos=int(may[(may.slug == slug) & may.en_ventana].shape[0]),
        sorteos_con_secos=with_secos,
        cobertura_secos_pct=round(100 * with_secos / len(exp), 1),
        filas_publicadas=len(s), secos_independientes=int((s.clase == "seco").sum()),
        derivados=int(s.clase.str.startswith("derivado").sum()),
        serie_000=int((s.clase == "serie_000_ambigua").sum()),
        otros_excluidos=int(s.clase.isin(["serie_faltante", "duplicado_en_sorteo", "invalido"]).sum()),
        sorteos_con_cuantia=int(len({d for (sl, d) in labeled_draws if sl == slug})),
        historial_desde=may[may.slug == slug].fecha.min(), mayores_historial=int((may.slug == slug).sum()),
    ))
inv = pd.DataFrame(inv)
inv.to_csv(os.path.join(OUT, "inventory.csv"), index=False)
pd.DataFrame(audit).to_csv(os.path.join(OUT, "audit_log.csv"), index=False)

summary = dict(
    sorteos_ventana=int(len(wd)), sorteos_con_secos=int(sec.groupby(["slug", "fecha"]).ngroups),
    filas_secos=int(len(sec)), clases=sec.clase.value_counts().to_dict(),
    mayores_total=int(len(may)), mayores_ventana=int(may.en_ventana.sum()),
    secos_con_cuantia=int(sec.amount_millions.notna().sum()),
    eventos_auditoria=pd.DataFrame(audit).tipo.value_counts().to_dict(),
)
json.dump(summary, open(os.path.join(OUT, "build_summary.json"), "w"), ensure_ascii=False, indent=1)
print(json.dumps(summary, ensure_ascii=False, indent=1))
print(cc.to_string(index=False))
