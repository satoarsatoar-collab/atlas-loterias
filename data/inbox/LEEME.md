# Carpeta de entrada

Suba aquí archivos `.csv` (o `.xlsx`) con resultados. En cada corrida el sistema los lee, los incorpora al almacén
(`data/store/resultados.csv`) sin duplicar lo que ya tenía y los mueve a `data/procesados/`.

Use `plantilla_resultados.csv` como modelo. Columnas:

| columna | ejemplo | nota |
|---|---|---|
| loteria | Medellín | también sirve `loteria-de-medellin`, `medellin`, `Lotería de Medellín` |
| fecha | 2026-10-23 | o `23/10/2026` |
| tipo | seco | `mayor` o `seco` (vacío = seco) |
| numero | 0047 | con sus ceros; si Excel los quita, se rellenan y se avisa |
| serie | 003 | con sus ceros |
| cuantia_millones | 10 | opcional; también acepta `$10.000.000` o `10 millones` |
| fuente | Telemedellín | opcional, recomendado |

Si una fila tiene un problema no se descarta en silencio: aparece en el tablero con el motivo.
