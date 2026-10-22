"""North Carolina counties by FIPS code.

An operational area is created from a point, with no county typed in. The
county is read off the structures themselves: USACE NSI gives each one its
census block (`cbfips`, 15 digits: state 2 + county 3 + tract 6 + block 4),
so the county most structures fall in names the area. No network call.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

# county FIPS (odd numbers 001..199) in the Census Bureau's own order
_NAMES = (
    "Alamance", "Alexander", "Alleghany", "Anson", "Ashe", "Avery", "Beaufort", "Bertie", "Bladen",
    "Brunswick", "Buncombe", "Burke", "Cabarrus", "Caldwell", "Camden", "Carteret", "Caswell",
    "Catawba", "Chatham", "Cherokee", "Chowan", "Clay", "Cleveland", "Columbus", "Craven",
    "Cumberland", "Currituck", "Dare", "Davidson", "Davie", "Duplin", "Durham", "Edgecombe",
    "Forsyth", "Franklin", "Gaston", "Gates", "Graham", "Granville", "Greene", "Guilford",
    "Halifax", "Harnett", "Haywood", "Henderson", "Hertford", "Hoke", "Hyde", "Iredell", "Jackson",
    "Johnston", "Jones", "Lee", "Lenoir", "Lincoln", "McDowell", "Macon", "Madison", "Martin",
    "Mecklenburg", "Mitchell", "Montgomery", "Moore", "Nash", "New Hanover", "Northampton",
    "Onslow", "Orange", "Pamlico", "Pasquotank", "Pender", "Perquimans", "Person", "Pitt", "Polk",
    "Randolph", "Richmond", "Robeson", "Rockingham", "Rowan", "Rutherford", "Sampson", "Scotland",
    "Stanly", "Stokes", "Surry", "Swain", "Transylvania", "Tyrrell", "Union", "Vance", "Wake",
    "Warren", "Washington", "Watauga", "Wayne", "Wilkes", "Wilson", "Yadkin", "Yancey",
)
NC_COUNTIES: dict[str, str] = {f"37{2 * i + 1:03d}": n for i, n in enumerate(_NAMES)}


def county_name(fips: str | None) -> str | None:
    """'37111' (or any longer census GEOID starting with it) -> 'McDowell'."""
    return NC_COUNTIES.get(str(fips)[:5]) if fips else None


def county_of(block_fips: Iterable[Any]) -> str:
    """The NC county most of these census-block codes fall in, or ''."""
    votes = Counter(n for n in (county_name(str(b)) for b in block_fips if b) if n)
    return votes.most_common(1)[0][0] if votes else ""
