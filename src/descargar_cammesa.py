"""
Descarga la demanda electrica del SADI (CAMMESA) con resolucion de 5 minutos.

Fuente: API publica de CAMMESA
    https://api.cammesa.com/demanda-svc/demanda/ObtieneDemandaYTemperaturaRegionByFecha
    parametros: id_region (int), fecha (YYYY-MM-DD)

Devuelve, por cada dia y region, ~288 registros con:
    fecha : timestamp cada 5 minutos (zona -03:00)
    dem   : demanda en MW
    temp  : temperatura en C (solo cada 15 minutos, el resto viene vacio)

Salida: data/raw/cammesa_demanda_5min.csv
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

BASE = "https://api.cammesa.com/demanda-svc/demanda/ObtieneDemandaYTemperaturaRegionByFecha"

# id_region -> nombre. Salen de https://api.cammesa.com/demanda-svc/demanda/RegionesDemanda
REGIONES = {
    1002: "SADI (total pais)",
    426: "GBA",
    425: "Buenos Aires",
    417: "Litoral",
    422: "Centro",
    419: "NOA",
    418: "NEA",
    429: "Cuyo",
    420: "Comahue",
    111: "Patagonia",
}

# La API solo devuelve datos del anio corriente.
DESDE = date(2026, 1, 1)
HASTA = date.today() - timedelta(days=1)

OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "cammesa_demanda_5min.csv"


def bajar_dia(args: tuple[int, date]) -> list[dict]:
    id_region, dia = args
    for intento in range(3):
        try:
            r = requests.get(
                BASE,
                params={"id_region": id_region, "fecha": dia.isoformat()},
                timeout=30,
            )
            r.raise_for_status()
            filas = r.json()
            for f in filas:
                f["id_region"] = id_region
                f["region"] = REGIONES[id_region]
            return filas
        except Exception:
            time.sleep(2 * (intento + 1))
    print(f"  ! fallo {REGIONES[id_region]} {dia}")
    return []


def main() -> None:
    dias = pd.date_range(DESDE, HASTA, freq="D").date
    tareas = [(rid, d) for rid in REGIONES for d in dias]
    print(f"{len(REGIONES)} regiones x {len(dias)} dias = {len(tareas)} pedidos")

    filas: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i, res in enumerate(pool.map(bajar_dia, tareas), 1):
            filas.extend(res)
            if i % 250 == 0:
                print(f"  {i}/{len(tareas)} pedidos - {len(filas):,} filas")

    df = pd.DataFrame(filas)
    df["fecha"] = pd.to_datetime(df["fecha"], format="ISO8601", utc=True).dt.tz_convert(
        "America/Argentina/Buenos_Aires"
    )
    df = df.rename(columns={"dem": "demanda_mw", "temp": "temperatura_c"})
    df = df[["fecha", "id_region", "region", "demanda_mw", "temperatura_c"]]
    df = df.sort_values(["region", "fecha"]).reset_index(drop=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"\nGuardado: {OUT}")
    print(f"Filas: {len(df):,} | Rango: {df.fecha.min()} -> {df.fecha.max()}")
    print(df.groupby("region")["demanda_mw"].agg(["count", "mean", "max"]))


if __name__ == "__main__":
    main()
