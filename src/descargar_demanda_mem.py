"""
Construye la serie horaria de demanda del MEM (total pais) desde 2021 hasta
el ultimo mes publicado, encadenando dos planillas oficiales de CAMMESA.

Fuentes (ambas en cammesaweb.cammesa.com, seccion Informes y Estadisticas):

  A. "Demanda Horaria por Tipo"
       Total pais, paso horario, ene-2023 -> ultimo mes cerrado.
       Trae la demanda separada en Distribuidores y Grandes Usuarios.

  B. "Planilla Demanda Horaria por Regiones"
       Total pais + 9 regiones, paso horario, ene-2021 -> dic-2023.

Ambas se solapan en 2023 y son identicas (verificado: diferencia maxima
0.04%). Para el total pais se usa B en 2021-2022 y A en 2023 en adelante,
porque A se actualiza todos los meses. La B ademas se guarda desagregada por
region para el EDA.

Convencion horaria de CAMMESA: HORA = 1..24, donde la hora h representa el
intervalo (h-1):00 a h:00. Se convierte a timestamp = fecha + (h-1) horas.
Argentina no tiene horario de verano desde 2009, asi que cada dia tiene
exactamente 24 horas y no hay que tratar cambios de huso.

Salidas:
    data/raw/cammesa_demanda_horaria_tipo_2023_2026.xlsx       (A, tal cual)
    data/raw/cammesa_demanda_horaria_regiones_2021_2023.xlsx   (B, tal cual)
    data/processed/demanda_horaria_mem.csv                     (serie total pais)
    data/processed/demanda_horaria_regiones_2021_2023.csv      (formato largo)
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests

BASE = Path(__file__).resolve().parents[1]
RAW = BASE / "data" / "raw"
PROCESSED = BASE / "data" / "processed"

# wpdmdl es el id del archivo en el gestor de descargas del sitio de CAMMESA.
URL_TIPO = "https://cammesaweb.cammesa.com/download/demanda-horaria/?wpdmdl=41424"
URL_REGIONES = "https://cammesaweb.cammesa.com/?wpdmdl=47560"

XLSX_TIPO = RAW / "cammesa_demanda_horaria_tipo_2023_2026.xlsx"
XLSX_REGIONES = RAW / "cammesa_demanda_horaria_regiones_2021_2023.xlsx"

REGIONES = {
    "BUENOS AIRES": "Buenos Aires",
    "CENTRO": "Centro",
    "COMAHUE": "Comahue",
    "CUYO": "Cuyo",
    "GRAN BS.AS.": "GBA",
    "LITORAL": "Litoral",
    "NORESTE": "NEA",
    "NOROESTE": "NOA",
    "PATAGONICA": "Patagonia",
}


def descargar(url: str, destino: Path) -> None:
    if destino.exists():
        print(f"  ya existe {destino.name}, no se vuelve a bajar")
        return
    print(f"  bajando {destino.name} ...")
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    contenido = r.content
    # La planilla por regiones viene comprimida en un zip con un unico xlsx.
    if contenido[:2] == b"PK" and "zip" in r.headers.get("content-type", ""):
        with zipfile.ZipFile(BytesIO(contenido)) as z:
            nombre = [n for n in z.namelist() if n.endswith(".xlsx")][0]
            contenido = z.read(nombre)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)


def a_timestamp(fecha: pd.Series, hora: pd.Series) -> pd.Series:
    return pd.to_datetime(fecha) + pd.to_timedelta(hora.astype(int) - 1, unit="h")


def leer_tipo(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, header=3)
    df.columns = [
        "anio", "mes", "n_mes", "n_dia", "tipo_dia", "dia_nombre",
        "fecha", "hora", "demanda_gu_mwh", "demanda_dist_mwh", "demanda_mwh",
    ]
    df = df.dropna(subset=["hora", "demanda_mwh"])
    df["timestamp"] = a_timestamp(df["fecha"], df["hora"])
    # CAMMESA escribe "Hábil" / "No Hábil" con mayusculas inconsistentes.
    df["tipo_dia"] = df["tipo_dia"].str.strip().str.lower().map({"hábil": "habil", "no hábil": "no_habil"})
    return df[["timestamp", "demanda_mwh", "demanda_dist_mwh", "demanda_gu_mwh", "tipo_dia"]]


def leer_regiones(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, header=11).iloc[:, :15]
    df.columns = ["anio", "mes", "fecha", "tipo_dia_detalle", "hora"] + list(REGIONES) + ["TOTAL"]
    df = df.dropna(subset=["hora", "TOTAL"])
    df["timestamp"] = a_timestamp(df["fecha"], df["hora"])
    # Esta planilla clasifica en 7 tipos (lunes habiles, ..., sabado, domingo o
    # feriado). Se reduce al mismo binario que la planilla A.
    df["tipo_dia"] = df["tipo_dia_detalle"].str.contains("Domingo|Sabado", case=False).map({True: "no_habil", False: "habil"})
    return df


def main() -> None:
    print("Descarga de planillas CAMMESA")
    descargar(URL_TIPO, XLSX_TIPO)
    descargar(URL_REGIONES, XLSX_REGIONES)

    print("\nLectura")
    tipo = leer_tipo(XLSX_TIPO)
    reg = leer_regiones(XLSX_REGIONES)
    print(f"  A (por tipo):     {len(tipo):,} horas, {tipo.timestamp.min()} -> {tipo.timestamp.max()}")
    print(f"  B (por regiones): {len(reg):,} horas, {reg.timestamp.min()} -> {reg.timestamp.max()}")

    # --- verificacion del solape: si no coinciden, no se pueden encadenar ---
    solape = tipo.merge(reg[["timestamp", "TOTAL"]], on="timestamp")
    diff_pct = ((solape["demanda_mwh"] - solape["TOTAL"]) / solape["TOTAL"]).abs().max() * 100
    print(f"  solape: {len(solape):,} horas, diferencia maxima {diff_pct:.3f}%")
    assert diff_pct < 0.5, "las dos planillas no coinciden en el periodo comun"

    # --- serie total pais: B hasta donde empieza A, A en adelante ---
    inicio_a = tipo["timestamp"].min()
    previo = reg.loc[reg["timestamp"] < inicio_a, ["timestamp", "TOTAL", "tipo_dia"]].rename(columns={"TOTAL": "demanda_mwh"})
    previo["fuente"] = "regiones_2021_2023"
    tipo["fuente"] = "por_tipo_2023_2026"
    mem = pd.concat([previo, tipo], ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    mem = mem[["timestamp", "demanda_mwh", "demanda_dist_mwh", "demanda_gu_mwh", "tipo_dia", "fuente"]]

    # --- serie regional en formato largo (una fila por region y hora) ---
    reg_largo = reg.melt(
        id_vars=["timestamp", "tipo_dia"], value_vars=list(REGIONES),
        var_name="region", value_name="demanda_mwh",
    )
    reg_largo["region"] = reg_largo["region"].map(REGIONES)
    reg_largo = reg_largo.sort_values(["region", "timestamp"]).reset_index(drop=True)

    assert mem["tipo_dia"].notna().all(), "quedaron tipos de dia sin mapear"

    PROCESSED.mkdir(parents=True, exist_ok=True)
    mem.to_csv(PROCESSED / "demanda_horaria_mem.csv", index=False, float_format="%.3f")
    reg_largo.to_csv(PROCESSED / "demanda_horaria_regiones_2021_2023.csv", index=False, float_format="%.3f")

    print("\nGuardado")
    print(f"  demanda_horaria_mem.csv: {len(mem):,} horas, {mem.timestamp.min()} -> {mem.timestamp.max()}")
    print(f"  demanda_horaria_regiones_2021_2023.csv: {len(reg_largo):,} filas")


if __name__ == "__main__":
    main()
