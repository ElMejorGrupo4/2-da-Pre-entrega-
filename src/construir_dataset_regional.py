"""
Construye data/processed/dataset_demanda_por_region.csv: demanda media diaria
de las 9 regiones del MEM (CAMMESA) con el clima diario de una estacion del
SMN por region.

Entradas (en data/raw/, no se versionan en git):
    Base Demanda Diaria 2017 2026.xlsx          CAMMESA, hoja "Datos Región" (MW medios por dia)
    smn_datos_meteorologicos_1991_2020.xlsx     SMN, datos diarios por estacion hasta 2020
    smn_datos_meteorologicos_desde_2021.lst     SMN, datos diarios por estacion desde 2021 (texto con tabuladores)

Salida:
    data/processed/dataset_demanda_por_region.csv   una fila por dia y region

Uso:
    python src/construir_dataset_regional.py

El script se detiene con AssertionError si alguna validacion falla, para no
generar en silencio un dataset con errores.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[1]
RAW = BASE / "data" / "raw"
SALIDA = BASE / "data" / "processed" / "dataset_demanda_por_region.csv"

XLSX_DEMANDA = RAW / "Base Demanda Diaria 2017 2026.xlsx"
XLSX_CLIMA_HASTA_2020 = RAW / "smn_datos_meteorologicos_1991_2020.xlsx"
LST_CLIMA_DESDE_2021 = RAW / "smn_datos_meteorologicos_desde_2021.lst"

# El SMN publica hasta 2026-06-30; la demanda de CAMMESA llega mas lejos, pero
# se corta aca para que todas las filas tengan la posibilidad de tener clima.
INICIO = pd.Timestamp("2017-01-01")
FIN = pd.Timestamp("2026-06-30")

REGIONES = [
    "GRAN BS.AS.", "BUENOS AIRES", "CENTRO", "LITORAL", "CUYO",
    "NOROESTE", "NORESTE", "COMAHUE", "PATAGONICA",
]

# Una estacion representativa seleccionada por region. Es una proxy del
# clima regional (limitacion espacial: una estacion no representa todo el
# territorio de regiones extensas como Patagonia o NOA). Se usa siempre la
# misma para que la serie no cambie de composicion con el tiempo (promediar
# "las que hayan medido ese dia" mezclaria climas distintos segun que
# estaciones reportaron).
# GBA usa Aeroparque (CABA) y la region Buenos Aires (resto de la provincia)
# usa La Plata: son regiones distintas en CAMMESA.
ESTACION_POR_REGION = {
    "GRAN BS.AS.": "AEROPARQUE AERO",
    "BUENOS AIRES": "LA PLATA AERO",
    "LITORAL": "ROSARIO AERO",
    "CENTRO": "CORDOBA AERO",
    "NOROESTE": "TUCUMAN AERO",
    "NORESTE": "RESISTENCIA AERO",
    "CUYO": "MENDOZA AERO",
    "COMAHUE": "NEUQUEN AERO",
    "PATAGONICA": "COMODORO RIVADAVIA AERO",
}

VARIABLES_CLIMA = [
    "TMAX", "TMIN", "TMEDIA", "PRECIP", "HELIOF", "VTO_MDIR",
    "VTO_MVEL", "VEL_MED", "PRE_EST", "HUM_REL", "NUB_TOT",
]

# Rangos fisicamente posibles para las estaciones elegidas. PRE_EST es presion
# a la altura de la estacion (no a nivel del mar): Mendoza, a ~700 m, ronda
# los 930 hPa, por eso el minimo es bajo.
RANGOS = {
    "TMAX": (-20, 50), "TMIN": (-30, 40), "TMEDIA": (-25, 45),
    "PRECIP": (0, 400), "HELIOF": (0, 24), "HUM_REL": (0, 100),
    "PRE_EST": (850, 1060), "VEL_MED": (0, 150), "VTO_MVEL": (0, 250),
    "NUB_TOT": (0, 8),
}

# Para detectar columnas corridas: la mediana de cada estacion no deberia
# moverse mas que esto entre 2017-2020 y 2021-2026. El parser viejo corria
# columnas y producia saltos de cientos de unidades (ej. presion 985 -> 180).
TOLERANCIA_MEDIANA = {"TMEDIA": 3, "PRE_EST": 10, "HUM_REL": 12, "VEL_MED": 8, "HELIOF": 3}


def limpiar_texto(df: pd.DataFrame) -> pd.DataFrame:
    """Quita espacios de columnas y valores; 'S/D' y vacios pasan a NaN."""
    df = df.copy()
    df.columns = df.columns.str.strip()
    for col in df.columns:
        if df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
            df[col] = df[col].astype("string").str.strip().replace({"S/D": pd.NA, "": pd.NA})
    return df


def a_numerico(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte las variables meteorologicas a float; lo que no es numero queda NaN."""
    df = df.copy()
    for col in VARIABLES_CLIMA:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def cargar_clima_hasta_2020() -> pd.DataFrame:
    # calamine lee este Excel de ~1 millon de filas en ~30 s (openpyxl tarda ~5 min).
    df = pd.read_excel(XLSX_CLIMA_HASTA_2020, sheet_name="Datos meteorológicos", engine="calamine")
    df = limpiar_texto(df).rename(columns={"NUB_TOTAL": "NUB_TOT"})
    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
    df = df[df["FECHA"] >= INICIO]
    return a_numerico(df)


def cargar_clima_desde_2021() -> pd.DataFrame:
    # El .lst esta separado por TABULADORES y un dato faltante es un campo
    # vacio entre dos tabs. Hay que leerlo con sep="\t": separar por "cualquier
    # espacio" (lo que hacia el notebook original) se come esos campos vacios
    # y corre todas las columnas siguientes un lugar a la izquierda.
    df = pd.read_csv(LST_CLIMA_DESDE_2021, sep="\t", encoding="utf-8", dtype=str, skip_blank_lines=True)
    df = limpiar_texto(df)
    # El archivo repite la fila de encabezado cada ~50.000 lineas.
    df = df[df["NRO_OMM"] != "NRO_OMM"]
    df["FECHA"] = pd.to_datetime(df["FECHA"], format="%d/%m/%Y", errors="coerce")
    assert df["FECHA"].notna().all(), "hay fechas del .lst que no se pudieron interpretar"
    return a_numerico(df)


def validar_clima(clima: pd.DataFrame) -> None:
    """Chequeos sobre las estaciones elegidas, antes de unir con la demanda."""
    print("\nValidacion del clima (estaciones elegidas)")
    estaciones = list(ESTACION_POR_REGION.values())
    sub = clima[clima["NOMBRE"].isin(estaciones)]

    faltan = set(estaciones) - set(sub["NOMBRE"])
    assert not faltan, f"estaciones sin datos: {faltan}"
    assert not sub.duplicated(["NOMBRE", "FECHA"]).any(), "hay estacion+fecha duplicadas"

    dias = sub.groupby("NOMBRE")["FECHA"].nunique()
    esperados = (FIN - INICIO).days + 1
    assert (dias == esperados).all(), f"estaciones con dias faltantes:\n{dias[dias != esperados]}"
    print(f"  9 estaciones con los {esperados:,} dias completos: OK")

    assert (sub["TMAX"] >= sub["TMIN"]).where(sub["TMAX"].notna() & sub["TMIN"].notna(), True).all(), "TMAX < TMIN"
    print("  TMAX >= TMIN: OK")

    for col, (lo, hi) in RANGOS.items():
        fuera = sub[col].notna() & ~sub[col].between(lo, hi)
        assert not fuera.any(), f"{col} fuera de [{lo}, {hi}]: {sub.loc[fuera, [col]].describe()}"
    # direccion del viento: el SMN la codifica en decenas de grados (1-36) y usa 99 para calma/variable
    mdir = sub["VTO_MDIR"].dropna()
    assert mdir.between(1, 36).where(mdir != 99, True).all(), "VTO_MDIR con codigos inesperados"
    print("  rangos fisicos (temperatura, humedad 0-100, heliofania 0-24, presion, viento, nubosidad): OK")

    # Comparacion de medianas antes/despues de 2021 por estacion.
    periodo = sub["FECHA"].dt.year.ge(2021).map({False: "2017-2020", True: "2021-2026"})
    med = sub.groupby(["NOMBRE", periodo])[list(TOLERANCIA_MEDIANA)].median().unstack()
    print("  medianas por estacion, antes/despues de 2021:")
    for col, tol in TOLERANCIA_MEDIANA.items():
        salto = (med[(col, "2021-2026")] - med[(col, "2017-2020")]).abs()
        assert (salto <= tol).all(), f"{col}: salto de mediana > {tol} en 2021 (columnas corridas?)\n{salto}"
        print(f"    {col:8s} salto maximo {salto.max():6.1f} (tolerancia {tol}): OK")


def construir_clima_regional(clima: pd.DataFrame) -> pd.DataFrame:
    """Una fila por region y fecha, tomada de la estacion asignada a la region."""
    estacion_a_region = {est: reg for reg, est in ESTACION_POR_REGION.items()}
    regional = clima[clima["NOMBRE"].isin(estacion_a_region)].copy()
    regional["zona"] = regional["NOMBRE"].map(estacion_a_region)
    regional = regional.rename(columns={"FECHA": "Fecha", "NOMBRE": "estacion_smn"})
    return regional[["Fecha", "zona", "estacion_smn"] + VARIABLES_CLIMA]


def cargar_demanda_regional() -> pd.DataFrame:
    df = pd.read_excel(XLSX_DEMANDA, sheet_name="Datos Región", header=4)
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    df = df[df["Fecha"].between(INICIO, FIN)]

    # Control de consistencia de la planilla: las regiones suman el total.
    dif = (df[REGIONES].sum(axis=1) - df["DEMANDA TOTAL"]).abs().max()
    assert dif < 1, f"las regiones no suman DEMANDA TOTAL (dif max {dif:.2f} MW)"

    # De formato ancho (una columna por region) a largo (una fila por region y dia).
    largo = df.melt(
        id_vars=["AÑO", "MES", "Fecha", "Tipo día"], value_vars=REGIONES,
        var_name="zona", value_name="demanda",
    )
    return largo


def unir_demanda_y_clima(demanda: pd.DataFrame, clima: pd.DataFrame) -> pd.DataFrame:
    # left: se conservan todas las filas de demanda. Si una fecha no tuviera
    # clima quedaria NaN (y se reporta), en vez de desaparecer como con inner.
    df = demanda.merge(clima, on=["Fecha", "zona"], how="left", validate="one_to_one")
    assert len(df) == len(demanda), "el merge cambio la cantidad de filas"
    return df


def validar_dataset(df: pd.DataFrame) -> None:
    print("\nValidacion del dataset final")
    assert sorted(df["zona"].unique()) == sorted(REGIONES), "no estan las 9 regiones"
    assert df["Fecha"].min() == INICIO and df["Fecha"].max() == FIN, "periodo distinto de 2017-01-01 -> 2026-06-30"
    dias = df.groupby("zona")["Fecha"].nunique()
    assert (dias == 3468).all(), f"regiones sin 3.468 dias:\n{dias}"
    assert len(df) == 31212, f"se esperaban 31.212 filas y hay {len(df):,}"
    assert not df.duplicated(["Fecha", "zona"]).any(), "hay Fecha+zona duplicadas"
    assert df["demanda"].notna().all() and (df["demanda"] > 0).all(), "demanda nula, negativa o cero"
    print("  9 regiones, 2017-01-01 -> 2026-06-30, 3.468 dias por region, 31.212 filas: OK")
    print("  sin duplicados de Fecha+zona, demanda sin nulos ni valores <= 0: OK")

    sin_clima = df["estacion_smn"].isna().sum()
    print(f"  filas de demanda sin clima: {sin_clima}")

    nulos = df.groupby("zona")[VARIABLES_CLIMA].apply(lambda g: g.isna().sum())
    print("\nNulos por variable y region:")
    print(nulos.to_string())
    print("\nTotal de nulos por variable:")
    print(df[VARIABLES_CLIMA].isna().sum().to_string())


def guardar_dataset(df: pd.DataFrame) -> None:
    columnas = ["AÑO", "MES", "Fecha", "Tipo día", "zona", "demanda", "estacion_smn"] + VARIABLES_CLIMA
    df = df[columnas].copy()
    df["MES"] = pd.to_datetime(df["MES"]).dt.date
    df["Fecha"] = df["Fecha"].dt.date
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SALIDA, index=False)
    print(f"\nGuardado: {SALIDA.relative_to(BASE)} ({len(df):,} filas)")


def main() -> None:
    print("Cargando clima SMN 2017-2020 ...")
    clima_a = cargar_clima_hasta_2020()
    print("Cargando clima SMN 2021-2026 ...")
    clima_b = cargar_clima_desde_2021()
    clima = pd.concat([clima_a, clima_b], ignore_index=True)
    clima = clima[clima["FECHA"].between(INICIO, FIN)]

    validar_clima(clima)
    clima_regional = construir_clima_regional(clima)

    print("\nCargando demanda regional CAMMESA ...")
    demanda = cargar_demanda_regional()

    df = unir_demanda_y_clima(demanda, clima_regional)
    validar_dataset(df)
    guardar_dataset(df)


if __name__ == "__main__":
    main()
