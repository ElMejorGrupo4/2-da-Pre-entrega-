"""
Descarga observaciones horarias del Servicio Meteorologico Nacional (SMN).

Fuente: datos abiertos del SMN, un archivo de texto de ancho fijo por dia
    https://ssl.smn.gob.ar/dpd/descarga_opendata.php?file=observaciones/datohorarioYYYYMMDD.txt

Cada archivo trae, para ~100 estaciones del pais y las 24 horas del dia:
    FECHA HORA TEMP HUM PNM DD FF NOMBRE
    (temperatura C, humedad %, presion a nivel del mar hPa,
     direccion del viento en grados, velocidad en km/h)

Salida: data/raw/smn_horario.csv
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

URL = "https://ssl.smn.gob.ar/dpd/descarga_opendata.php?file=observaciones/datohorario{}.txt"

DESDE = date(2026, 1, 1)
HASTA = date.today() - timedelta(days=1)

# Estaciones de interes. Vacio = todas.
ESTACIONES = [
    "AEROPARQUE AERO",
    "EZEIZA AERO",
    "ROSARIO AERO",
    "CORDOBA AERO",
    "MENDOZA AERO",
    "TUCUMAN AERO",
    "RESISTENCIA AERO",
    "NEUQUEN AERO",
    "COMODORO RIVADAVIA AERO",
    "LA PLATA AERO",
]

COLSPECS = [(0, 8), (8, 14), (14, 20), (20, 26), (26, 33), (33, 39), (39, 45), (45, 100)]
NOMBRES = ["fecha", "hora", "temperatura_c", "humedad_pct", "presion_hpa", "viento_dir_gr", "viento_vel_kmh", "estacion"]

OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "smn_horario.csv"


def bajar_dia(dia: date) -> pd.DataFrame | None:
    for intento in range(3):
        try:
            r = requests.get(URL.format(dia.strftime("%Y%m%d")), timeout=45)
            r.raise_for_status()
            texto = r.content.decode("latin-1")
            if len(texto) < 500:
                return None
            df = pd.read_fwf(
                StringIO(texto),
                colspecs=COLSPECS,
                names=NOMBRES,
                skiprows=2,
                dtype={"fecha": str},
            )
            df["estacion"] = df["estacion"].str.strip()
            if ESTACIONES:
                df = df[df["estacion"].isin(ESTACIONES)]
            return df
        except Exception:
            time.sleep(2 * (intento + 1))
    print(f"  ! fallo {dia}")
    return None


def main() -> None:
    dias = list(pd.date_range(DESDE, HASTA, freq="D").date)
    print(f"{len(dias)} dias a descargar")

    partes: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i, res in enumerate(pool.map(bajar_dia, dias), 1):
            if res is not None:
                partes.append(res)
            if i % 50 == 0:
                print(f"  {i}/{len(dias)} dias")

    df = pd.concat(partes, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["fecha"], format="%d%m%Y") + pd.to_timedelta(
        pd.to_numeric(df["hora"], errors="coerce"), unit="h"
    )
    df = df.drop(columns=["fecha", "hora"])
    df = df[["timestamp", "estacion", "temperatura_c", "humedad_pct", "presion_hpa", "viento_dir_gr", "viento_vel_kmh"]]
    df = df.dropna(subset=["timestamp"]).sort_values(["estacion", "timestamp"]).reset_index(drop=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"\nGuardado: {OUT}")
    print(f"Filas: {len(df):,} | Rango: {df.timestamp.min()} -> {df.timestamp.max()}")
    print(df.groupby("estacion")["temperatura_c"].agg(["count", "mean", "min", "max"]))


if __name__ == "__main__":
    main()
