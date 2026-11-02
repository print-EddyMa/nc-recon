"""Storm cases. Each is a real event: ERA5 initial state, NOAA IBTrACS best track,
and an NC-relevant target the objective is measured over."""
from dataclasses import dataclass, field
from pathlib import Path

WORK = Path(__file__).resolve().parent / "work"
IBTRACS_URL = ("https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/"
               "v04r01/access/csv/ibtracs.NA.list.v04r01.csv")   # full North Atlantic record


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
    model: str = "deterministic_2_8_deg"
    objective_short: str = ""          # e.g. "Moisture into WNC" (web stat label)
    impact_unit: str = "kg m⁻¹ s⁻¹"


CASES = {
    "helene": Case(
        id="helene", name="Hurricane Helene (2024)", sid="2024268N17278",
        init="2024-09-24T12:00",
        forcing_times=("2024-09-24T00:00", "2024-09-25T00:00", "2024-09-26T00:00",
                       "2024-09-27T00:00", "2024-09-28T00:00"),
        storm0=(19.2, -83.7),
        target=(35.65, -82.35), target_label="Western NC (Asheville / Old Fort)",
        objective="ivt", objective_label="moisture transport (IVT) into western NC",
        objective_short="Moisture into WNC",
        notes="Init as a 40-kt tropical storm in the NW Caribbean; window spans Big Bend "
              "landfall (+60 h) to the core crossing the southern Appalachians (+72-78 h).",
    ),
    "helene-rain": Case(
        id="helene-rain", name="Hurricane Helene (2024) · rainfall", sid="2024268N17278",
        init="2024-09-24T12:00",
        forcing_times=("2024-09-24T00:00", "2024-09-25T00:00", "2024-09-26T00:00",
                       "2024-09-27T00:00", "2024-09-28T00:00"),
        storm0=(19.2, -83.7),
        target=(35.65, -82.35), target_label="Western NC (Asheville / Old Fort)",
        objective="rain", objective_label="rainfall over western NC, +24-78 h (25 Sep 12Z - 27 Sep 18Z)",
        objective_short="Rain over WNC", impact_unit="mm", window=(24, 78),
        model="stochastic_precip_2_8_deg",
        notes="Same start as the moisture case, but the objective is the rain itself: NeuralGCM's "
              "precipitation-trained model, fixed random key, accumulated over the predecessor-rain "
              "and core-rain period.",
    ),
    "florence": Case(
        id="florence", name="Hurricane Florence (2018)", sid="2018242N13343",
        init="2018-09-11T12:00",
        forcing_times=("2018-09-11T00:00", "2018-09-12T00:00", "2018-09-13T00:00",
                       "2018-09-14T00:00", "2018-09-15T00:00"),
        storm0=(26.5, -64.7),
        target=(34.6, -78.5), target_label="Southeastern NC (Wilmington / Lumberton)",
        objective="ivt", objective_label="moisture transport (IVT) into southeastern NC",
        objective_short="Moisture into SE NC",
        notes="Init as a Cat 4 over the open Atlantic; window spans landfall near Wrightsville Beach "
              "(14 Sep ~11Z) and the start of the stall that flooded southeastern NC.",
    ),
    "matthew": Case(
        id="matthew", name="Hurricane Matthew (2016)", sid="2016273N13300",
        init="2016-10-06T00:00",
        forcing_times=("2016-10-06T00:00", "2016-10-07T00:00", "2016-10-08T00:00",
                       "2016-10-09T00:00", "2016-10-10T00:00"),
        storm0=(23.0, -76.0),
        target=(34.9, -78.6), target_label="Eastern NC (Lumberton / Goldsboro)",
        objective="ivt", objective_label="moisture transport (IVT) into eastern NC",
        objective_short="Moisture into E NC",
        notes="Init as a Cat 3 over the Bahamas; window spans the closest approach to NC "
              "(8 Oct 12Z - 9 Oct 06Z), when the Lumberton and Neuse floods' rain fell.",
    ),
    "michael": Case(
        id="michael", name="Hurricane Michael (2018)", sid="2018280N18273",
        init="2018-10-08T12:00",
        forcing_times=("2018-10-08T00:00", "2018-10-09T00:00", "2018-10-10T00:00",
                       "2018-10-11T00:00", "2018-10-12T00:00"),
        storm0=(20.9, -85.1),
        target=(35.7, -80.3), target_label="NC Piedmont",
        objective="ivt", objective_label="moisture transport (IVT) into the NC Piedmont",
        objective_short="Moisture into NC Piedmont",
        notes="Init as a 65-kt hurricane near the Yucatán Channel; window spans its crossing of "
              "GA, SC and central NC as a tropical storm (11 Oct).",
    ),
    "milton": Case(
        id="milton", name="Hurricane Milton (2024)", sid="2024279N21265",
        init="2024-10-07T00:00",
        forcing_times=("2024-10-07T00:00", "2024-10-08T00:00", "2024-10-09T00:00",
                       "2024-10-10T00:00", "2024-10-11T00:00"),
        storm0=(22.5, -93.4),
        target=(27.95, -82.46), target_label="Tampa Bay",
        objective="wind", objective_label="925/850-hPa wind energy over Tampa Bay", radius_km=250.0,
        objective_short="Wind energy over Tampa Bay", impact_unit="m² s⁻²",
        notes="Out-of-state validation case (not shown in the NC app).",
    ),
}


def besttrack(case: Case):
    """6-hourly NOAA IBTrACS best track for the case (downloads + caches the CSV)."""
    import pandas as pd, urllib.request
    WORK.mkdir(parents=True, exist_ok=True)
    csv = WORK / "ibtracs_NA.csv"
    if not csv.exists():
        urllib.request.urlretrieve(IBTRACS_URL, csv)
    df = pd.read_csv(csv, skiprows=[1], low_memory=False, keep_default_na=False, na_values=[" ", ""])
    m = df[df.SID == case.sid][["ISO_TIME", "LAT", "LON", "USA_WIND", "USA_PRES", "USA_SSHS"]].copy()
    m["ISO_TIME"] = pd.to_datetime(m.ISO_TIME)
    m = m[(m.ISO_TIME.dt.minute == 0) & (m.ISO_TIME.dt.hour % 6 == 0)]
    for c in ["LAT", "LON", "USA_WIND", "USA_PRES"]:
        m[c] = pd.to_numeric(m[c], errors="coerce")
    return m.reset_index(drop=True)
