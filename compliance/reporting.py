"""Standards-mapped compliance reporting for the workspace governance view.

Replaces the previous "Control Matrix" in ``views/governance_center.py``,
which listed four controls with no reference to any actual standard
("Executive reporting cadence", "Connected cloud estates", ...) and graded
them against arbitrary thresholds invented for the demo. Every control
below cites the real standard clause it maps to and is graded from data
the workspace actually has -- see docs/COMPLIANCE_MAPPING.md for the full
standard-by-standard writeup this module implements against:

* GHG Protocol Corporate Accounting and Reporting Standard + Scope 2 Guidance
* ISO 14064-1:2018
* CSRD / ESRS E1 (Climate change)
* GRI 305: Emissions 2016
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ControlStatus:
    control: str
    standard_reference: str
    status: str  # "Healthy" | "Partial" | "Watch" | "Missing"
    evidence: str


def data_quality_summary(breakdown: dict[str, int]) -> dict[str, Any]:
    """Turn a {tier: count} breakdown into a disclosure-ready summary.

    ISO 14064-1:2018 clause 5.2 (and the GHG Protocol's data quality
    guidance) expect an inventory to characterize the quality of its
    activity data rather than presenting every figure as equally certain.
    """
    total = sum(breakdown.values())
    if total == 0:
        return {"total_records": 0, "high_pct": 0.0, "medium_pct": 0.0, "low_pct": 0.0, "unknown_pct": 0.0}
    return {
        "total_records": total,
        "high_pct": breakdown.get("high", 0) / total * 100,
        "medium_pct": breakdown.get("medium", 0) / total * 100,
        "low_pct": breakdown.get("low", 0) / total * 100,
        "unknown_pct": breakdown.get("unknown", 0) / total * 100,
    }


def standards_control_checklist(
    *,
    headline: dict[str, Any],
    data_quality: dict[str, Any],
    market_instrument_count: int,
) -> list[ControlStatus]:
    """Build the governance control matrix, grounded in real standards.

    ``headline`` is ``DashboardService.get_workspace_snapshot(org_id)["headline"]``.
    ``data_quality`` is the output of :func:`data_quality_summary`.
    """
    controls: list[ControlStatus] = []

    # --- GHG Protocol Scope 2 dual reporting -------------------------------
    has_telemetry = headline.get("total_carbon", 0) > 0 or headline.get("connectors", 0) > 0
    if not has_telemetry:
        scope2_status = "Missing"
        scope2_evidence = "No carbon telemetry has been ingested yet, so no Scope 2 figures exist to dual-report."
    elif market_instrument_count > 0:
        scope2_status = "Healthy"
        scope2_evidence = (
            f"Location-based Scope 2 is calculated for every connected account using sourced regional grid "
            f"factors; {market_instrument_count} renewable energy contract(s)/certificate(s) are on file, "
            "enabling a real market-based figure per GHG Protocol Scope 2 Guidance."
        )
    else:
        scope2_status = "Partial"
        scope2_evidence = (
            "Location-based Scope 2 is calculated for every connected account using sourced regional grid "
            "factors (EPA eGRID / EEA / Google / EMA Singapore). No renewable energy contracts are recorded, "
            "so market-based reporting currently falls back to the location-based figure rather than "
            "reflecting actual purchasing decisions -- record a PPA/REC to close this gap."
        )
    controls.append(
        ControlStatus(
            control="Scope 2 dual reporting (location-based & market-based)",
            standard_reference="GHG Protocol Scope 2 Guidance (2015), Ch. 4",
            status=scope2_status,
            evidence=scope2_evidence,
        )
    )

    # --- ISO 14064-1:2018 data quality management ---------------------------
    total_records = data_quality.get("total_records", 0)
    high_medium_pct = data_quality.get("high_pct", 0) + data_quality.get("medium_pct", 0)
    if total_records == 0:
        dq_status = "Missing"
        dq_evidence = "No standardized ingestion records exist yet to assess data quality against."
    elif high_medium_pct >= 80:
        dq_status = "Healthy"
        dq_evidence = (
            f"{high_medium_pct:.0f}% of {total_records} ingested telemetry records resolved a real "
            "instance type and provider region (high/medium confidence); the remainder used documented "
            "default assumptions, disclosed rather than presented as measured."
        )
    elif high_medium_pct >= 40:
        dq_status = "Watch"
        dq_evidence = (
            f"Only {high_medium_pct:.0f}% of {total_records} ingested records resolved real instance/region "
            "data; a large share relies on documented default assumptions (2 vCPU, 50% utilization)."
        )
    else:
        dq_status = "Partial"
        dq_evidence = (
            f"{data_quality.get('unknown_pct', 0):.0f}% of {total_records} records predate standardized "
            "ingestion and carry no recorded data-quality tier."
        )
    controls.append(
        ControlStatus(
            control="Activity data quality management",
            standard_reference="ISO 14064-1:2018, clause 5.2",
            status=dq_status,
            evidence=dq_evidence,
        )
    )

    # --- CSRD / ESRS E1-5: energy consumption and mix ------------------------
    controls.append(
        ControlStatus(
            control="Energy consumption disclosure",
            standard_reference="CSRD / ESRS E1-5",
            status="Partial" if has_telemetry else "Missing",
            evidence=(
                "Total facility energy (kWh, PUE-adjusted) is tracked per workload via the standardized "
                "engine. Renewable-vs-non-renewable energy mix requires contract/REC data (see Scope 2 "
                "control above) and is not yet disclosed separately."
                if has_telemetry
                else "No energy telemetry has been ingested yet."
            ),
        )
    )

    # --- CSRD / ESRS E1-6: gross Scopes 1/2/3 GHG emissions ------------------
    controls.append(
        ControlStatus(
            control="Gross GHG emissions disclosure (Scopes 1/2/3)",
            standard_reference="CSRD / ESRS E1-6",
            status="Partial" if has_telemetry else "Missing",
            evidence=(
                "Scope 2 (purchased cloud compute/storage/network energy) is quantified with dual "
                "location-/market-based reporting. Scope 1 is not applicable (no direct fuel combustion in "
                "cloud-only operations). Scope 3 is limited to this tool's own cloud-service boundary and "
                "does not cover other upstream/downstream categories the standard requires for a full "
                "corporate inventory."
            ),
        )
    )

    # --- GRI 305: Emissions ---------------------------------------------------
    reports_count = headline.get("reports", 0)
    controls.append(
        ControlStatus(
            control="Emissions disclosure evidence library",
            standard_reference="GRI 305: Emissions (2016)",
            status="Healthy" if reports_count else "Missing",
            evidence=(
                f"{reports_count} published report(s) available as disclosure evidence."
                if reports_count
                else "No governance report has been published yet."
            ),
        )
    )

    # --- ISO 14064-1:2018 organizational roles -------------------------------
    team_members = headline.get("team_members", 0)
    controls.append(
        ControlStatus(
            control="Organizational roles & responsibilities",
            standard_reference="ISO 14064-1:2018, clause 5.1",
            status="Healthy" if team_members >= 3 else "Partial",
            evidence=f"{team_members} active workspace member(s) assigned to the carbon accounting program.",
        )
    )

    return controls
