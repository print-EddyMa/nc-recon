"""Storm cases. Each is a real event: ERA5 initial state, NOAA IBTrACS best track,
and an NC-relevant target the objective is measured over."""
from dataclasses import dataclass, field
from pathlib import Path

WORK = Path(__file__).resolve().parent / "work"
IBTRACS_URL = ("https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/"
               "v04r01/access/csv/ibtracs.last3years.list.v04r01.csv")


@dataclass(frozen=True)
class Case:
    id: str
    name: str
    sid: str                       # IBTrACS storm id
    init: str                      # ERA5 initial time (UTC)
    forcing_times: tuple           # daily SST / sea-ice times spanning the forecast
    storm0: tuple                  # (lat, lon) of the storm at init, from the best track
    target: tuple                  # (lat, lon) centre of the impact region
    target_label: str
    objective: str                 # "ivt": moisture transport (flood rain) | "wind": low-level wind energy
    objective_label: str
    radius_km: float = 220.0       # Gaussian radius of the impact region
    hours: int = 78
    every: int = 6
    window: tuple = (60, 66, 72, 78)   # forecast hours the objective is summed over
    keep_out_km: float = 600.0         # no nudging this close to the storm itself
    notes: str = ""


CASES = {
    "helene": Case(
        id="helene", name="Hurricane Helene (2024)", sid="2024268N17278",
        init="2024-09-24T12:00",
        forcing_times=("2024-09-24T00:00", "2024-09-25T00:00", "2024-09-26T00:00",
                       "2024-09-27T00:00", "2024-09-28T00:00"),
        storm0=(19.2, -83.7),
        target=(35.65, -82.35), target_label="Western NC (Asheville / Old Fort)",
        objective="ivt", objective_label="moisture transport (IVT) into western NC",
        notes="Init as a 40-kt tropical storm in the NW Caribbean; window spans Big Bend "
              "landfall (+60 h) to the core crossing the southern Appalachians (+72-78 h).",
    ),
    "milton": Case(
        id="milton", name="Hurricane Milton (2024)", sid="2024279N21265",
        init="2024-10-07T00:00",
        forcing_times=("2024-10-07T00:00", "2024-10-08T00:00", "2024-10-09T00:00",
                       "2024-10-10T00:00", "2024-10-11T00:00"),
        storm0=(22.5, -93.4),
        target=(27.95, -82.46), target_label="Tampa Bay",
        objective="wind", objective_label="925/850-hPa wind energy over Tampa Bay", radius_km=250.0,
        notes="Out-of-state validation case (not shown in the NC app).",
    ),
}


def besttrack(case: Case):
    """6-hourly NOAA IBTrACS best track for the case (downloads + caches the CSV)."""
    import pandas as pd, urllib.request
    WORK.mkdir(parents=True, exist_ok=True)
    csv = WORK / "ibtracs_last3years.csv"
    if not csv.exists():
        urllib.request.urlretrieve(IBTRACS_URL, csv)
    df = pd.read_csv(csv, skiprows=[1], low_memory=False, keep_default_na=False, na_values=[" ", ""])
    m = df[df.SID == case.sid][["ISO_TIME", "LAT", "LON", "USA_WIND", "USA_PRES", "USA_SSHS"]].copy()
    m["ISO_TIME"] = pd.to_datetime(m.ISO_TIME)
    m = m[(m.ISO_TIME.dt.minute == 0) & (m.ISO_TIME.dt.hour % 6 == 0)]
    for c in ["LAT", "LON", "USA_WIND", "USA_PRES"]:
        m[c] = pd.to_numeric(m[c], errors="coerce")
    return m.reset_index(drop=True)
