"""GHG Protocol Scope 2 dual reporting.

Implements the location-based / market-based split required by the
`GHG Protocol Scope 2 Guidance <https://ghgprotocol.org/sites/default/files/2023-03/Scope%202%20Guidance.pdf>`_
(2015, still the current corporate accounting standard as of this
writing). Every cloud carbon number this app previously produced was, in
GHG Protocol terms, a location-based estimate with no market-based
counterpart and no visibility into which method was even being used --
dual reporting is one of the standard's core requirements for anyone who
has purchased renewable energy attributes.

Market-based accounting requires evidence of a contractual instrument
(a PPA, a supplier-specific emission factor, or unbundled Energy
Attribute Certificates/RECs). This app has no such contract data model
yet, so :func:`scope2_dual_report` is built to accept one when available
and to fall back honestly to the location-based figure (flagged as a
fallback, not silently presented as a market-based result) otherwise --
see ``docs/ROADMAP.md`` for the planned "renewable energy contracts"
follow-up.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

from engine.emission_factors import get_regional_intensity

MarketInstrumentType = Literal["ppa", "supplier_specific", "energy_attribute_certificate", "residual_mix"]

# GHG Protocol Scope 2 Guidance quality hierarchy for market-based
# accounting, most preferred first.
MARKET_INSTRUMENT_QUALITY_RANK: dict[MarketInstrumentType, int] = {
    "ppa": 1,
    "supplier_specific": 2,
    "energy_attribute_certificate": 3,
    "residual_mix": 4,
}


class MarketInstrument(TypedDict, total=False):
    """A recorded renewable-energy contract/certificate applicable to a workload."""

    type: MarketInstrumentType
    co2e_per_kwh: float
    source: str
    covered_kwh: float | None  # None means "covers this workload fully"


@dataclass
class Scope2Result:
    energy_kwh: float
    location_based_kg_co2e: float
    location_based_source: str
    market_based_kg_co2e: float
    market_based_method: str
    dual_reporting_complete: bool


def scope2_dual_report(
    *,
    energy_kwh: float,
    provider: str,
    region_code: str,
    market_instrument: MarketInstrument | None = None,
) -> Scope2Result:
    """Compute both required GHG Protocol Scope 2 figures for one workload's energy use.

    ``market_instrument`` is the only way to produce a real market-based
    number below the location-based one; without it the market-based
    figure equals the location-based figure and is labeled as a fallback,
    which is the standard's prescribed behavior when no contractual
    instrument is on file (GHG Protocol Scope 2 Guidance, Ch. 4).
    """
    intensity = get_regional_intensity(provider, region_code)
    location_based_kg = energy_kwh * intensity.co2e_per_kwh

    if market_instrument and market_instrument.get("co2e_per_kwh") is not None:
        market_based_kg = energy_kwh * float(market_instrument["co2e_per_kwh"])
        method = f"{market_instrument.get('type', 'unknown')} ({market_instrument.get('source', 'unspecified source')})"
        dual_complete = True
    else:
        market_based_kg = location_based_kg
        method = "location_based_fallback (no contractual instrument on file for this workload)"
        dual_complete = False

    return Scope2Result(
        energy_kwh=energy_kwh,
        location_based_kg_co2e=location_based_kg,
        location_based_source=f"{intensity.source} ({intensity.quality_tier})",
        market_based_kg_co2e=market_based_kg,
        market_based_method=method,
        dual_reporting_complete=dual_complete,
    )


def aggregate_scope2(results: list[Scope2Result]) -> dict[str, float | int]:
    """Roll up a batch of Scope 2 results into inventory-level totals."""
    if not results:
        return {
            "total_energy_kwh": 0.0,
            "total_location_based_kg_co2e": 0.0,
            "total_market_based_kg_co2e": 0.0,
            "workloads_with_market_instrument": 0,
            "workloads_total": 0,
            "market_instrument_coverage_pct": 0.0,
        }
    with_instrument = sum(1 for r in results if r.dual_reporting_complete)
    return {
        "total_energy_kwh": sum(r.energy_kwh for r in results),
        "total_location_based_kg_co2e": sum(r.location_based_kg_co2e for r in results),
        "total_market_based_kg_co2e": sum(r.market_based_kg_co2e for r in results),
        "workloads_with_market_instrument": with_instrument,
        "workloads_total": len(results),
        "market_instrument_coverage_pct": (with_instrument / len(results)) * 100,
    }
