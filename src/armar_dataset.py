"""
Une demanda (CAMMESA), clima (SMN) y feriados en una unica tabla horaria.

Entradas:  data/raw/cammesa_demanda_5min.csv
           data/raw/smn_horario.csv
Salida:    data/processed/dataset_demanda_horaria.csv

Grano: una fila por region y hora.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

BASE = Path(__file__).resolve().parents[1]
RAW = BASE / "data" / "raw"
OUT = BASE / "data" / "processed" / "dataset_demanda_horaria.csv"

# Cada region del SADI se apareja con la estacion meteorologica de su
# ciudad cabecera. Es una aproximacion: hay que dejarla escrita en el README.
ESTACION_POR_REGION = {
    "GBA": "AEROPARQUE AERO",
    "Buenos Aires": "LA PLATA AERO",
    "Litoral": "ROSARIO AERO",
    "Centro": "CORDOBA AERO",
    "NOA": "TUCUMAN AERO",
    "NEA": "RESISTENCIA AERO",
    "Cuyo": "MENDOZA AERO",
    "Comahue": "NEUQUEN AERO",
    "Patagonia": "COMODORO RIVADAVIA AERO",
    "SADI (total pais)": "EZEIZA AERO",
}

TEMP_CONFORT = 18.0  # C, base para grados-dia


def feriados(anio: int) -> set[pd.Timestamp]:
    try:
        r = requests.get(f"https://api.argentinadatos.com/v1/feriados/{anio}", timeout=20)
        r.raise_for_status()
        return {pd.Timestamp(f["fecha"]).normalize() for f in r.json()}
    except Exception as e:
        print(f"  ! no se pudieron bajar feriados ({e}); columna en 0")
        return set()


def main() -> None:
    # --- demanda: de 5 minutos a horaria ---
    dem = pd.read_csv(RAW / "cammesa_demanda_5min.csv", parse_dates=["fecha"])
    dem["timestamp"] = dem["fecha"].dt.tz_localize(None).dt.floor("h")
    dem = (
        dem.groupby(["region", "timestamp"])
        .agg(demanda_mw=("demanda_mw", "mean"), demanda_pico_mw=("demanda_mw", "max"))
        .round(1)
        .reset_index()
    )
    print(f"demanda horaria: {len(dem):,} filas")

    # --- clima ---
    smn = pd.read_csv(RAW / "smn_horario.csv", parse_dates=["timestamp"])
    smn = smn.drop(columns=["viento_dir_gr"])

    dem["estacion"] = dem["region"].map(ESTACION_POR_REGION)
    df = dem.merge(smn, on=["estacion", "timestamp"], how="left")

    # --- calendario ---
    fer = feriados(2026)
    df["hora"] = df["timestamp"].dt.hour
    df["dia_semana"] = df["timestamp"].dt.dayofweek
    df["es_finde"] = (df["dia_semana"] >= 5).astype(int)
    df["es_feriado"] = df["timestamp"].dt.normalize().isin(fer).astype(int)

    # --- grados-dia: la relacion demanda/temperatura es una U, no una recta ---
    df["cdd"] = (df["temperatura_c"] - TEMP_CONFORT).clip(lower=0).round(2)
    df["hdd"] = (TEMP_CONFORT - df["temperatura_c"]).clip(lower=0).round(2)

    # --- lags: la baseline convertida en feature ---
    df = df.sort_values(["region", "timestamp"])
    g = df.groupby("region")["demanda_mw"]
    df["dem_lag_24h"] = g.shift(24)
    df["dem_lag_168h"] = g.shift(168)

    cols = [
        "timestamp", "region", "estacion",
        "demanda_mw", "demanda_pico_mw",
        "temperatura_c", "humedad_pct", "presion_hpa", "viento_vel_kmh",
        "hora", "dia_semana", "es_finde", "es_feriado",
        "cdd", "hdd", "dem_lag_24h", "dem_lag_168h",
    ]
    df = df[cols].reset_index(drop=True)

    df.to_csv(OUT, index=False)
    print(f"\nGuardado: {OUT}")
    print(f"{len(df):,} filas x {len(df.columns)} columnas")
    print(f"Rango: {df.timestamp.min()} -> {df.timestamp.max()}\n")
    print(df.isna().sum().to_frame("nulos").assign(pct=lambda d: (d.nulos / len(df) * 100).round(1)))


if __name__ == "__main__":
    main()
