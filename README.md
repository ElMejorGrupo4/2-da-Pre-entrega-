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
| CAMMESA (demanda diaria por región) + SMN (clima) — `dataset_demanda_por_region.csv` | Demanda media diaria de las 9 regiones con temperatura, humedad, viento, presión, etc. | ene-2017 → jun-2026 | Análisis regional y fuente de temperatura |
| CAMMESA — API de demanda (5 min) | Demanda por región cada 5 minutos | 2026 (año corriente) | Complementario |
| SMN — observaciones horarias | Temperatura, humedad, presión, viento en ~10 estaciones | 2026 | Complementario |

Las dos planillas de CAMMESA coinciden hora a hora en el año que se solapan (2023, diferencia máxima 0,04 %), por lo que se encadenan en una única serie continua de **48.912 horas (2021-01-01 → 2026-07-31), sin huecos ni nulos**.

El dataset regional diario se validó contra esa serie: sumando las 9 regiones por día coincide con el promedio diario de la serie horaria (diferencia máxima 0,38 %). De sus variables climáticas, **solo las temperaturas son confiables**: el resto cambia de escala en 2021 por un problema al unir los dos archivos del SMN (pendiente de revisión).

**Alcance elegido:** total país (MEM). Es la serie que CAMMESA efectivamente pronostica para el despacho, y es la única con más de 5 años de historia horaria continua y actualización mensual.

## Estructura del repositorio

```
Proyecto Final/
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
    ├── descargar_cammesa.py       # API 5 min por región (año corriente)
    ├── descargar_smn.py           # observaciones horarias del SMN
    └── armar_dataset.py           # une API 5 min + SMN (dataset regional 2026)
```

## Cómo reproducir

```bash
pip install -r requirements.txt
python src/descargar_demanda_mem.py     # genera data/processed/demanda_horaria_mem.csv
jupyter notebook notebooks/01_eda_inicial.ipynb
```

## Avance por pre-entregas

- [x] **Pre-entrega 1 — Estructura, datos y EDA inicial.** Repo armado, serie horaria 2021–2026 construida y validada (granularidad, huecos, duplicados, nulos), primeras visualizaciones: distribución, serie completa y tendencia interanual, estacionalidad mensual, curva diaria (hábil/no hábil, verano/invierno), perfil semanal, mapa de calor hora × mes y análisis regional complementario. Ver `notebooks/01_eda_inicial.ipynb`.
- [ ] Pre-entrega 2 — Limpieza y enriquecimiento con clima.
- [ ] Pre-entrega 3 — Clustering de días típicos (K-means, DBSCAN).
- [ ] Pre-entrega 4 — Modelos supervisados (Regresión Lineal, Random Forest).
- [ ] Pre-entrega 5 — Explicabilidad (SHAP) y plus de IA.
- [ ] Pre-entrega 6 — Documentación, sesgos y cierre.

## Principales hallazgos del EDA

- La demanda va de ~9.300 a ~28.100 MW (media ~16.000), con tres estacionalidades superpuestas: diaria (valle 3–6 h), semanal (hábil > sábado > domingo) y anual con **dos picos**, verano (ene–feb) e invierno (jun–jul).
- **La hora del pico depende de la estación:** a la tarde (14–16 h) en verano, a la noche (20–21 h) en invierno. Esta interacción hora × temporada justifica probar modelos no lineales.
- Todas las horas récord de la serie son tardes hábiles de febrero (olas de calor). Se conservan: son los eventos que más importa acertar.
- GBA + Litoral + Buenos Aires concentran el 61 % de la demanda nacional, por lo que la temperatura de la región pampeana es la variable climática natural para el total país.
- La demanda tiene forma de **U** con la temperatura (mínimo en ~16–17 °C en GBA). La correlación lineal casi no la detecta, lo que refuerza el uso de modelos no lineales o de variables de grados-día.

## Integrantes

- Juan Serrano

## Nota sobre feriados y tipo de día

CAMMESA clasifica cada día como *hábil* o *no hábil* (sábados, domingos y feriados) en sus propias planillas. Se adopta esa clasificación en lugar de construir un calendario de feriados propio, porque refleja el criterio que usa el operador para programar el despacho.
