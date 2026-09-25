# Forecast de demanda eléctrica del MEM argentino

Proyecto final del curso de Data Science — Programa Energía Digital 2026 (Fundación YPF + Jump Educación).

## El problema

CAMMESA, el operador del Mercado Eléctrico Mayorista (MEM), tiene que garantizar en todo momento que la generación iguale a la demanda: la electricidad no se almacena a escala de red. Para eso programa el despacho del día siguiente en base a un pronóstico de demanda. Cuanto mejor es ese pronóstico, menos reserva térmica hay que mantener encendida "por las dudas", con el consiguiente ahorro económico y de emisiones.

**Objetivo del modelo:** predecir la demanda eléctrica horaria del MEM (MWh) para las próximas 24 horas, a partir de variables de calendario (hora, día de semana, mes, tipo de día) y climáticas (temperatura).

## Datos

| Fuente | Contenido | Período | Uso |
|---|---|---|---|
| CAMMESA — "Demanda Horaria por Tipo" | Demanda real neta total del MEM, paso horario, desagregada en Distribuidores y Grandes Usuarios | ene-2023 → jul-2026 | Base del modelo |
| CAMMESA — "Demanda Horaria por Regiones" | Total MEM + 9 regiones, paso horario | ene-2021 → dic-2023 | Base del modelo (2021–2022) y análisis regional |
| CAMMESA (demanda diaria por región) + SMN (clima diario) — `dataset_demanda_por_region.csv` | Demanda media diaria de las 9 regiones con temperatura, humedad, viento, presión, etc. de una estación representativa del SMN por región | ene-2017 → jun-2026 | EDA regional (no es insumo del modelo horario) |

Las dos planillas de CAMMESA coinciden hora a hora en el año que se solapan (2023, diferencia máxima 0,04 %), por lo que se encadenan en una única serie continua de **48.912 horas (2021-01-01 → 2026-07-31), sin huecos ni nulos**.

El dataset regional diario se validó contra esa serie: sumando las 9 regiones por día coincide con el promedio diario de la serie horaria (diferencia máxima 0,38 %).

**Alcance elegido:** total país (MEM). Es la serie que CAMMESA efectivamente pronostica para el despacho, y es la única con más de 5 años de historia horaria continua y actualización mensual.

### Dataset regional diario con clima

Lo arma `src/construir_dataset_regional.py` a partir de tres archivos crudos, que van en `data/raw/`:

| Archivo | Procedencia | Contenido |
|---|---|---|
| `Base Demanda Diaria 2017 2026.xlsx` | CAMMESA — [Comportamiento de la demanda de energía eléctrica en el MEM](https://cammesaweb.cammesa.com/2026/09/18/covid-19-comportamiento-de-la-demanda-de-energia-electrica-en-el-mem/) | Hoja "Datos Región": demanda neta diaria por región en MW medios, tipo de día y temperatura de referencia de GBA |
| `smn_datos_meteorologicos_1991_2020.xlsx` | SMN — [descarga de datos](https://ws2.smn.gob.ar/descarga-de-datos) | Datos diarios por estación 1991–2020 (se usa desde 2017) |
| `smn_datos_meteorologicos_desde_2021.lst` | SMN — [descarga de datos](https://ws2.smn.gob.ar/descarga-de-datos) | Datos diarios por estación desde 2021, en texto separado por tabuladores |

Transformación, resumida:

1. **Clima.** Se leen los dos archivos del SMN. El `.lst` se lee **respetando los tabuladores**: un dato faltante es un campo vacío entre dos tabs, y separarlo por "cualquier espacio" (como hacía la primera versión) corre las columnas. Se eliminan las filas de encabezado que el archivo repite, se limpian espacios y `S/D` pasa a NaN. En `PRECIP`, según el diccionario de datos del SMN, una celda vacía es un día sin lluvia y se carga como 0 mm. Fechas a `datetime` y variables a numéricas.
2. **Una estación representativa seleccionada por región** (ver criterio abajo).
3. **Demanda.** La hoja "Datos Región" pasa de formato ancho (una columna por región) a largo (una fila por día y región), dentro de 2017-01-01 → 2026-06-30 (fin del dato del SMN).
4. **Unión** por fecha y región con *left merge*: se conservan todas las filas de demanda, y si faltara clima quedaría NaN y se reportaría.
5. **Validaciones:** 9 regiones, 3.468 días por región, 31.212 filas, sin duplicados de fecha + región, demanda positiva, TMAX ≥ TMIN, humedad 0–100, heliofanía 0–24, rangos físicos de temperatura, presión y viento, y comparación de medianas antes y después de 2021 para detectar columnas corridas. Si alguna falla, el script se detiene sin guardar.

**Criterio de estaciones por región.** Se usa siempre la misma estación representativa seleccionada por región. No se promedian "las estaciones que midieron ese día": la composición cambiaría con el tiempo y mezclaría climas distintos según qué estaciones reportaron.

| Región CAMMESA | Estación SMN |
|---|---|
| GRAN BS.AS. | AEROPARQUE AERO |
| BUENOS AIRES (resto de la provincia) | LA PLATA AERO |
| LITORAL | ROSARIO AERO |
| CENTRO | CORDOBA AERO |
| NOROESTE | TUCUMAN AERO |
| NORESTE | RESISTENCIA AERO |
| CUYO | MENDOZA AERO |
| COMAHUE | NEUQUEN AERO |
| PATAGONICA | COMODORO RIVADAVIA AERO |

**Limitación:** cada estación es una **proxy** del clima de su región. Regiones extensas como Patagonia, NOA o Comahue abarcan climas muy distintos y una sola estación no los representa a todos. Es una limitación espacial del dataset.

**Uso:** este dataset diario se usa para el **EDA regional**. El futuro modelo horario va a necesitar temperatura **horaria**; repetir la `TMEDIA` del día en las 24 horas perdería la variación dentro del día, que es la que mueve la curva de carga.

Las 9 estaciones tienen los 3.468 días del período y `TMEDIA` no tiene faltantes, así que no hicieron falta estaciones de respaldo. Los faltantes que hay (`HELIOF` y algunos `TMAX`/`TMIN`) quedan como NaN, sin imputar. Para GBA se evaluó la temperatura de referencia de CAMMESA: está muy correlacionada con Aeroparque (0,986), pero Aeroparque explica un poco mejor la demanda de GBA y mantiene la misma fuente para las 9 regiones.

## Estructura del repositorio

```
2-da-Pre-entrega-/
├── README.md
├── requirements.txt
├── data/
│   ├── raw/          # descargas sin modificar (no versionadas en git)
│   └── processed/    # datasets construidos (serie horaria MEM, regional horaria 2021-23, regional diaria con clima)
├── notebooks/        # numerados por etapa
│   └── 01_eda_inicial.ipynb
├── reports/
│   └── figures/      # gráficos exportados por los notebooks
└── src/
    ├── descargar_demanda_mem.py   # baja las planillas CAMMESA y arma la serie 2021-2026
    └── construir_dataset_regional.py  # arma el dataset regional diario con clima (CAMMESA + SMN)
```

## Cómo reproducir

```bash
pip install -r requirements.txt
python src/descargar_demanda_mem.py        # genera data/processed/demanda_horaria_mem.csv
python src/construir_dataset_regional.py   # genera data/processed/dataset_demanda_por_region.csv
jupyter notebook notebooks/01_eda_inicial.ipynb
```

`data/raw/` no se versiona en git (archivos pesados). `descargar_demanda_mem.py` baja sus planillas solo; para `construir_dataset_regional.py` hay que descargar los tres archivos crudos de las fuentes de arriba y copiarlos en `data/raw/` con esos nombres.

## Principales hallazgos del EDA

- La demanda va de ~9.300 a ~28.100 MW (media ~16.000), con tres estacionalidades superpuestas: diaria (valle 3–6 h), semanal (hábil > sábado > domingo) y anual con **dos picos**, verano (ene–feb) e invierno (jun–jul).
- **La hora del pico depende de la estación:** a la tarde (14–16 h) en verano, a la noche (20–21 h) en invierno. Esta interacción hora × temporada justifica probar modelos no lineales.
- Todas las horas récord de la serie son tardes hábiles de febrero (olas de calor). Se conservan: son los eventos que más importa acertar.
- GBA + Litoral + Buenos Aires concentran el 61 % de la demanda nacional, por lo que la temperatura de la región pampeana es la variable climática natural para el total país.
- La demanda tiene forma de **U** con la temperatura (mínimo en ~19 °C de temperatura media en GBA). La correlación lineal casi no la detecta, lo que refuerza el uso de modelos no lineales o de variables de grados-día.
- Las 11 variables climáticas del SMN quedaron alineadas y son consistentes en 2017–2026, pero no todas están listas para modelar: `HELIOF`, `TMAX` y `TMIN` tienen faltantes.

## Integrantes

- Juan Serrano
- Rodrigo Duarte

## Nota sobre feriados y tipo de día

CAMMESA clasifica cada día como *hábil* o *no hábil* (sábados, domingos y feriados) en sus propias planillas. Se adopta esa clasificación en lugar de construir un calendario de feriados propio, porque refleja el criterio que usa el operador para programar el despacho.
