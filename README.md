# ATLAS · laboratorio de patrones en loterías colombianas

Sistema que **guarda cada resultado nuevo** de las 14 loterías tradicionales (premio mayor y secos), **genera y
combina cientos de patrones** (cifras, terminaciones, sumas, estructuras, calientes/fríos, arrastres, Markov…)
y los **califica con datos que todavía no existían** cuando se hizo la predicción. Publica un tablero web y un resumen
que se actualizan solos.

> **Lo honesto primero.** El estudio previo (carpeta `estudio/`) no encontró ninguna regularidad que resista una
> corrección por comparaciones múltiples ni una validación en datos nuevos, y comprar billetes devuelve en promedio
> 31-34 % de lo que cuestan. Este sistema no "adivina" números: está diseñado para que, si algún patrón real
> existiera, se note, y para que el azar no lo engañe a usted haciéndose pasar por patrón.

## Qué hace cada corrida

1. **Descarga** los sorteos publicados en LoteríaYa que aún no tiene (`atlas/scrape.py`).
2. **Lee** los archivos que usted subió a `data/inbox/` (`atlas/ingest.py`).
3. **Guarda** todo en un solo archivo, `data/store/resultados.csv`, sin duplicar: los números y series siempre como
   texto (`0047`), y con la fuente de cada fila.
4. **Audita**: separa los secos que no son extracciones independientes (permutaciones del mayor, mayor ± 1,
   permutaciones de otro seco, duplicados, serie 000), porque crean patrones falsos (`atlas/build.py`).
5. **Busca patrones** (`atlas/patterns.py`): 838 reglas × 16 grupos (todas las loterías, cada una, menor cuantía) y
   255 combinadores que las mezclan. Antes de cada sorteo, cada regla apuesta una distribución de probabilidad usando
   solo sorteos anteriores; su puntaje **E** multiplica cuánto más probable le pareció el resultado real que al azar.
6. **Predice** los próximos sorteos con los combinadores y **guarda la predicción con huella SHA-256** en
   `state/predicciones/` antes de conocer el resultado. Luego compara (`state/registro_aciertos.csv`).
7. **Publica** el tablero (`site/index.html`) y un resumen legible en GitHub (`state/RESUMEN.md`). Si un patrón queda
   validado, abre un *issue* para avisarle.

### Números posibles

El tablero tiene una sección para cada sorteo próximo con seis listas de 10 números: el **combinador ATLAS**,
**calientes**, **recientes**, **fríos**, **del mayor anterior** (ese número y combinaciones de sus cifras) y una lista
**al azar** que sirve de grupo de control. Un marcador lleva la cuenta de cuántas veces acertó cada método frente a lo
esperado por suerte, en el historial, en los datos nuevos y en las listas guardadas con huella antes de cada sorteo. Hay
también un buscador: escriba un número y verá cuántas veces ha salido, la última vez y en qué listas aparece.

«Acertar» significa que el número de 4 cifras salió en un seco con cualquier serie; para cobrar hace falta además la
serie. Mientras ningún método le gane a la lista al azar con el paso de las semanas, todos valen lo mismo.

### Series

Cada lotería juega un rango de series (por ejemplo, Medellín 000-499). Las series entran al motor como cualquier otro
rasgo, siempre dentro de cada lotería: última cifra de la serie, franja del rango (décimos) y serie completa, con reglas
calientes, recientes, frías y «la serie del mayor anterior». El combinador sugiere 10 series por sorteo frente a 10 series
al azar, y la sección «Series: ¿salen todas por igual?» prueba, lotería por lotería, si alguna serie o franja sale más de
lo normal (con corrección por comparaciones múltiples). El buscador acepta número y serie: dice si ese billete exacto ha
ganado un seco y cuántas veces salió esa serie.

### Por qué no se deja engañar

- Con sorteos aleatorios, E vale 1 en promedio y la probabilidad de que **alguna vez** llegue a 20 es menor que
  1 / 20, por más veces que se mire (desigualdad de Ville). Por eso puede revisarse a diario sin inflar errores.
- Con más de mil patrones a la vez, varios cruzarán 20 por suerte; para **validar** se usa e-BH al 10 % (tasa de
  falsos descubrimientos), que hoy exige E ≥ 10.920 al mejor patrón.
- El combinador principal (números de los secos, todas las loterías) se fijó de antemano como prueba única.
- Solo cuenta lo ocurrido desde el **17-oct-2026**; lo anterior ya se miró en el estudio.
- Pruebas automáticas (`tests/`) comprueban que con datos simulados al azar no se valida nada y que un sesgo fuerte
  sí se detecta. En simulación, si en una lotería la última cifra 4 saliera el doble de lo normal (20 %), el sistema lo
  validaría en unas 10 semanas; un sesgo de 1,5× puede tardar más de 40 semanas; uno menor es invisible con estos
  volúmenes de datos.

## Instalación (elija una opción)

### Opción A — GitHub con tablero público (gratis, recomendada)

1. Cree un repositorio **público** vacío en GitHub (por ejemplo `atlas-loterias`).
2. Suba todos los archivos de esta carpeta. Desde un computador con git:
   ```bash
   git init && git add -A && git commit -m "ATLAS"
   git branch -M main
   git remote add origin https://github.com/SU_USUARIO/atlas-loterias.git
   git push -u origin main
   ```
   (Sin git: en GitHub, *Add file → Upload files* y arrastre el contenido de la carpeta. Asegúrese de que se suba la
   carpeta oculta `.github/`.)
3. En el repositorio: **Settings → Pages → Source: GitHub Actions**.
4. En **Actions**, habilite los flujos si se lo pide y ejecute **ATLAS → Run workflow** una vez.
5. El tablero queda en `https://SU_USUARIO.github.io/atlas-loterias/`. Se actualiza solo a las 00:15 y 06:30
   (hora de Colombia) y cada vez que usted sube un archivo a `data/inbox/`.

Un repositorio público deja ver a cualquiera los datos y el tablero (no contienen información personal).

### Opción B — GitHub privado

Igual que la A, pero con el repositorio **privado**. GitHub Actions sigue funcionando (el plan gratuito incluye
2.000 minutos al mes para repositorios privados; cada corrida tarda 1-2 minutos). GitHub Pages no está disponible en
repositorios privados del plan gratuito, así que el paso «publicar» fallará sin afectar lo demás. Vea los resultados en
`state/RESUMEN.md` (GitHub lo muestra formateado, también en la app del celular) o descargue el artefacto
`atlas-tablas` de cada corrida y abra `site/index.html`.

### Opción C — Su propia nube (VPS, Raspberry Pi, NAS) con Docker

```bash
git clone https://github.com/SU_USUARIO/atlas-loterias.git && cd atlas-loterias
echo "ATLAS_TOKEN=una-clave-larga-que-usted-elija" > .env
docker compose up -d
```

- Tablero: `http://IP-DEL-SERVIDOR:8080`. Se recalcula cada 6 horas (`ATLAS_CADA_HORAS`).
- Subir resultados desde el celular: `http://IP-DEL-SERVIDOR:8080/subir` (pide la clave de `ATLAS_TOKEN`). También
  puede copiar archivos a `data/inbox/` por cualquier medio (SFTP, Syncthing, carpeta compartida).
- Los datos viven en las carpetas `data/`, `state/` y `site/` del servidor, fuera del contenedor.
- Si lo expone a internet, póngalo detrás de HTTPS (por ejemplo Caddy o un túnel de Cloudflare).

Sin Docker: `pip install -r requirements.txt && python -m atlas.servidor`.

## Confirmar y agregar resultados desde el tablero

- **Últimos sorteos**: cada sorteo de los últimos 8 días con su premio mayor, sus secos, la fuente y un enlace para
  verificarlo en LoteríaYa. Los que no tienen secos traen un botón «Agregar secos».
- **Agregar resultados**: elija lotería y fecha, pegue la lista de secos como la copie de la página de la lotería
  (un premio por línea: número, serie y, si lo sabe, el valor), pulse «Revisar» y luego «Guardar en GitHub». Se abre su
  repositorio con el archivo listo en `data/inbox/`; solo pulse **Commit changes** (GitHub le pide su sesión, así que solo
  usted puede agregar). Si el archivo aparece vacío, pegue con Cmd + V: el botón también lo copia. Alternativa: «Descargar
  CSV» y subirlo con *Add file → Upload files*.

## Agregar resultados a mano

Copie `data/inbox/plantilla_resultados.csv`, llénelo y súbalo a `data/inbox/` (en GitHub: *Add file → Upload files*).

```csv
loteria,fecha,tipo,numero,serie,cuantia_millones,fuente
Medellín,2026-10-23,mayor,0123,045,,Lotería de Medellín
Medellín,2026-10-23,seco,0047,003,10,Telemedellín
```

- `tipo`: `mayor` o `seco`. `cuantia_millones` es opcional pero valiosa: LoteríaYa no publica el valor de cada seco,
  y sin él no se pueden seguir los patrones de menor cuantía.
- Si un resultado ya estaba guardado no se duplica; si su archivo trae la cuantía, se completa.
- Si dos fuentes no coinciden, se conserva el dato guardado y el conflicto aparece en el tablero.
- Las filas con problemas (lotería desconocida, fecha futura, número inválido…) aparecen en el tablero con el motivo.

## Uso local

```bash
pip install -r requirements-dev.txt
python -m atlas.pipeline --scrape no     # solo con lo que haya en data/inbox/
python -m atlas.pipeline                 # con descarga automática
python -m pytest tests
```

## Estructura

```
atlas/                 sistema
  config.py            loterías, días de juego, festivos de Colombia, umbrales
  store.py             almacén único y reglas para no duplicar
  ingest.py            lectura de data/inbox/ (CSV o Excel)
  scrape.py            descarga desde LoteríaYa
  build.py             auditoría y clasificación de filas
  patterns.py          reglas, combinadores, e-valores y e-BH
  dashboard.py         tablero HTML y resumen Markdown
  pipeline.py          ciclo completo
  servidor.py          modo nube propia (Docker)
data/store/            resultados.csv: todos los datos (se versiona)
data/inbox/            aquí se suben archivos nuevos
data/procesados/       archivos ya incorporados
state/                 predicciones con huella, registro de aciertos, RESUMEN.md
site/                  tablero publicado
estudio/               estudio original: código, datos crudos, resultados y pre-registro (ver estudio/README.md)
tests/                 pruebas
.github/workflows/     automatización en GitHub
```

## Limitaciones

- **La descarga automática no se probó contra el sitio en vivo** (el entorno donde se construyó no tenía salida a
  internet); se probó contra una copia sintética del formato observado en octubre de 2026. Si el sitio cambia o bloquea
  la descarga, el tablero lo muestra en «Descarga automática» y el sistema sigue funcionando con lo que usted suba.
  Revise los primeros sorteos descargados contra la página oficial.
- LoteríaYa no publica secos de todos los sorteos (Tolima, Quindío y Cruz Roja tienen huecos); súbalos a mano si los
  consigue en otra fuente.
- e-BH se aplica sobre los valores del momento; el umbral individual (E ≥ 20) sí es válido aunque se mire cada día.
  Trate cualquier «validado» como una pista que debe seguir sosteniéndose, no como una certeza.
- Un patrón validado no implica ganancia: tendría además que multiplicar por más de 3 la probabilidad de ganar para
  compensar el margen de la lotería y los impuestos (ver «¿Vale la pena comprar?» en el tablero).
- En repositorios públicos, GitHub puede pausar las tareas programadas tras 60 días sin actividad; si pasa, reactívelas
  en **Actions**.
