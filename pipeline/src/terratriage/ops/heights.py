"""Typed heights: five different things all called "height" or "level".

    EllipsoidalHeight  raw GNSS h, in a named frame (NAD83(2011) / ITRF2014)
    Elevation          orthometric H in NAVD88 (H = h - N, GEOID18 N)
    TidalLevel         relative to a local tidal datum (MLLW, MHHW, MSL ...)
    GaugeStage         height above a specific gauge's own datum
    Depth              water above ground, or above the first floor

The code cannot add a gauge stage to an elevation, compare stages from two
different gauges, or subtract an ellipsoidal height from an elevation: every
cross-type operation needs an explicit conversion that names its datum. All
values are stored in metres; constructors take a unit so feet never leak in.
"""
from __future__ import annotations

from dataclasses import dataclass

from .geodesy import INTL_FOOT_M, US_SURVEY_FOOT_M

_UNIT = {"m": 1.0, "ft": INTL_FOOT_M, "ftUS": US_SURVEY_FOOT_M, "in": INTL_FOOT_M / 12.0}


class HeightTypeError(TypeError):
    pass


def _to_m(value: float, unit: str) -> float:
    if unit not in _UNIT:
        raise ValueError(f"unknown unit {unit!r}; use one of {sorted(_UNIT)}")
    return float(value) * _UNIT[unit]


@dataclass(frozen=True)
class _Height:
    m: float

    def to(self, unit: str) -> float:
        return self.m / _UNIT[unit]

    def _same(self, other: object) -> None:
        if type(other) is not type(self):
            raise HeightTypeError(
                f"cannot combine {type(self).__name__} with {type(other).__name__}; "
                "convert explicitly through a datum"
            )

    def __add__(self, other):  # noqa: D401
        raise HeightTypeError(
            f"cannot add to a {type(self).__name__}; add a Depth to an Elevation "
            "with Elevation.plus_depth(), or convert through a datum"
        )

    __radd__ = __add__

    def __sub__(self, other):
        raise HeightTypeError(f"use an explicit method to difference {type(self).__name__}")

    def __lt__(self, other):
        self._same(other)
        return self.m < other.m

    def __le__(self, other):
        self._same(other)
        return self.m <= other.m


@dataclass(frozen=True)
class EllipsoidalHeight(_Height):
    frame: str = "NAD83(2011)"

    @classmethod
    def of(cls, value: float, unit: str = "m", frame: str = "NAD83(2011)"):
        return cls(_to_m(value, unit), frame)

    def to_navd88(self, geoid_undulation_m: float, geoid_model: str = "GEOID18") -> "Elevation":
        """H = h - N. In NC, N is about -30 to -35 m, so forgetting this step
        shows up as a ~30 m "error"."""
        if geoid_model == "GEOID18" and self.frame != "NAD83(2011)":
            raise HeightTypeError(
                f"GEOID18 is defined against NAD83(2011), not {self.frame}; "
                "transform the frame first"
            )
        return Elevation(self.m - geoid_undulation_m, datum="NAVD88", geoid=geoid_model)


@dataclass(frozen=True)
class Elevation(_Height):
    datum: str = "NAVD88"
    geoid: str | None = None

    @classmethod
    def of(cls, value: float, unit: str = "m", datum: str = "NAVD88"):
        return cls(_to_m(value, unit), datum)

    def _same(self, other: object) -> None:
        super()._same(other)
        if other.datum != self.datum:  # type: ignore[attr-defined]
            raise HeightTypeError(f"datum mismatch {self.datum} vs {other.datum}")  # type: ignore[attr-defined]

    def minus(self, other: "Elevation") -> "Depth":
        """Water surface elevation minus a ground/floor elevation -> depth."""
        self._same(other)
        return Depth(self.m - other.m, reference="elevation difference")

    def plus_depth(self, d: "Depth") -> "Elevation":
        if not isinstance(d, Depth):
            raise HeightTypeError("plus_depth needs a Depth")
        return Elevation(self.m + d.m, datum=self.datum, geoid=self.geoid)


@dataclass(frozen=True)
class GaugeStage(_Height):
    gauge_id: str = ""

    @classmethod
    def of(cls, value: float, gauge_id: str, unit: str = "ft"):
        if not gauge_id:
            raise ValueError("a stage is meaningless without its gauge id")
        return cls(_to_m(value, unit), gauge_id)

    def _same(self, other: object) -> None:
        super()._same(other)
        if other.gauge_id != self.gauge_id:  # type: ignore[attr-defined]
            raise HeightTypeError(
                f"stages from different gauges ({self.gauge_id} vs {other.gauge_id}) "  # type: ignore[attr-defined]
                "are not comparable; convert both to NAVD88 first"
            )

    def to_elevation(self, gauge_datum: Elevation) -> Elevation:
        """stage + gauge datum elevation -> water-surface elevation."""
        if not isinstance(gauge_datum, Elevation):
            raise HeightTypeError("gauge datum must be an Elevation (with its vertical datum)")
        return Elevation(gauge_datum.m + self.m, datum=gauge_datum.datum)


@dataclass(frozen=True)
class TidalLevel(_Height):
    datum: str = "MHHW"
    station: str = ""

    def to_navd88(self, datum_offset_navd88_m: float) -> Elevation:
        """Level + (tidal datum's NAVD88 elevation at this station), from CO-OPS/VDatum."""
        return Elevation(self.m + datum_offset_navd88_m, datum="NAVD88")


@dataclass(frozen=True)
class Depth(_Height):
    reference: str = "ground"  # "ground" | "first_floor" | "elevation difference"

    @classmethod
    def of(cls, value: float, unit: str = "m", reference: str = "ground"):
        return cls(_to_m(value, unit), reference)
