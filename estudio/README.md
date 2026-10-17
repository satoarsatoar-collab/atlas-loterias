# Proyecto ATLAS — laboratorio estadístico de loterías colombianas

Código, datos y resultados del estudio sobre los premios secos de las 14 loterías tradicionales
(17-ago a 16-oct-2026) y los premios mayores (nov-2024 a oct-2026).

## Estructura

```
data/raw/hist_<loteria>.csv          premios mayores (LoteríaYa /historial)
data/raw/ly/<loteria>_<fecha>.txt    secos de cada sorteo (LoteríaYa /resultado/<fecha>)
data/raw/labeled/<fuente>_...csv     secos con cuantía (Telemedellín, Vanguardia, Radio Nacional, resultadosloteriascol.com)
data/raw/window_draws.csv            calendario de los 124 sorteos del período
data/processed/                      datasets auditados (mayores.csv, secos.csv), inventario y bitácora de auditoría
out/                                 resultados: hipótesis, validación, economía, pre-registro
src/                                 código
```

Todos los números y series se guardan como **texto** (0047 ≠ 47).

## Cómo reproducir (Python 3.10+)

```bash
pip install numpy scipy pandas scikit-learn
cd estudio/src
python build_dataset.py      # dataset auditado + inventario + bitácora (≈ 2 s)
python analysis.py           # batería de hipótesis exploración/confirmación con Holm y BH (≈ 1 min)
python null_simulation.py    # sesgo de selección bajo azar puro (≈ 5 min)
python descriptive.py        # frecuencias con IC simultáneos y potencia
python replication.py        # replicación independiente en Bogotá de las pistas de menor cuantía (≈ 30 s)
python models.py             # validación walk-forward de 9 modelos (≈ 15 s)
python economics.py          # valor esperado exacto por enumeración de billetes (≈ 15 s)
python prospective.py registrar   # nuevo pre-registro con huella SHA-256
```

Estos ocho scripts se ejecutaron y produjeron los archivos de `out/` incluidos.

## Actualizar con sorteos nuevos

```bash
pip install requests lxml
# (la descarga de sorteos nuevos ahora la hace el sistema principal: python -m atlas.pipeline)
python build_dataset.py && python analysis.py && python models.py
python prospective.py evaluar ../out/preregistro_2026-10-17.json nuevos_resultados.csv
```

`nuevos_resultados.csv` lleva columnas `loteria_slug,fecha,tipo,numero,serie,cuantia_millones`
(`tipo` = `mayor` o `seco`). La cuantía solo es necesaria para la hipótesis H1.

## Reglas de clasificación de filas (auditoría)

Las listas públicas de "secos" mezclan premios que **no** son extracciones independientes. Una fila se excluye del análisis si:

| clase | regla |
|---|---|
| `derivado_permutacion_mayor` | misma serie que el mayor y mismos dígitos en otro orden |
| `derivado_mayor_pm1` | misma serie que el mayor y número = mayor ± 1 |
| `derivado_permutacion_seco` | misma serie y mismos dígitos que un seco anterior del mismo sorteo |
| `duplicado_en_sorteo` | número y serie idénticos a otra fila del mismo sorteo |
| `serie_000_ambigua` | serie 000 (en Manizales la segunda fuente la excluye en 5 de 5 sorteos) |
| `serie_faltante` | fila sin serie |

## Fuentes

- LoteríaYa: https://www.loteriaya.com.co/ (resultados, historial, plan de premios, guía de impuestos)
- Telemedellín (secos de Lotería de Medellín con cuantía), Vanguardia y Radio Nacional (Lotería de Manizales con cuantía),
  resultadosloteriascol.com (Lotería de Boyacá con cuantía; CSV abierto CC BY 4.0),
  bogota.gov.co y Vanguardia (Lotería de Bogotá con cuantía; conjunto de replicación)
