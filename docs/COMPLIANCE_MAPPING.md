# Compliance Standards Mapping

This document maps Cloud Carbon Tracker's features to the real
international standards a carbon-accounting tool is expected to align
with, and is honest about what is and isn't covered yet. It is the source
the Governance Center's control matrix (`views/governance_center.py`,
built from `compliance/reporting.py`) is generated from — nothing in that
UI should assert compliance the codebase can't actually back up.

## Standards in scope

| Standard | What it requires | Where this app addresses it |
|---|---|---|
| [GHG Protocol Corporate Standard](https://ghgprotocol.org/corporate-standard) | Organizational/operational boundary, Scope 1/2/3 categorization | Scope 2 is the primary category this tool addresses (purchased cloud compute/storage/network energy). Scope 1 is not applicable to cloud-only operations. Scope 3 beyond the cloud-service boundary is out of scope. |
| [GHG Protocol Scope 2 Guidance](https://ghgprotocol.org/sites/default/files/2023-03/Scope%202%20Guidance.pdf) (2015) | Dual reporting: location-based *and* market-based Scope 2 | `compliance/ghg_protocol.scope2_dual_report()`. Location-based always available (sourced grid factors). Market-based requires a recorded renewable energy contract (`RenewableContractService` / `renewable_energy_contracts` table); without one, the result is explicitly flagged as a location-based fallback, not silently presented as market-based. |
| [ISO 14064-1:2018](https://www.iso.org/standard/66453.html) | Organizational GHG inventory: boundaries, data quality management (clause 5.2), roles & responsibilities (clause 5.1) | Every ingested record carries a `data_quality` tier (`high`/`medium`/`low`) recording whether the real instance type and region were resolved or a documented default was used (`engine/standardized_carbon_engine.py`). Aggregated and disclosed via `compliance.reporting.data_quality_summary()`. |
| [CSRD / ESRS E1](https://www.efrag.org/) (EU Corporate Sustainability Reporting Directive, Climate change standard) | E1-5: energy consumption & mix. E1-6: gross Scope 1/2/3 GHG emissions with intensity ratios. | E1-5: total facility energy (kWh, PUE-adjusted) is tracked; renewable/non-renewable *mix* requires contract data (same gap as Scope 2 market-based above). E1-6: Scope 2 dual-reported as above; other ESRS E1 disclosure requirements (E1-1 transition plan, E1-4 targets, E1-8 internal carbon pricing, etc.) are organizational/strategic disclosures outside a telemetry tool's scope and are not addressed here. |
| [GRI 305: Emissions](https://www.globalreporting.org/) (2016) | Emissions disclosure with supporting evidence | The Reporting Library / saved reports feature (`SavedReportService`) is the evidence trail; the control matrix reports whether any evidence exists. |

## What "compliant" does and doesn't mean here

This tool **calculates real, sourced emissions estimates and produces
disclosure-ready figures aligned with the structure these standards
expect.** It does **not** constitute a certified GHG inventory or an
audited CSRD disclosure on its own — that requires an assured
organizational boundary, verified primary activity data (not
provider-sourced averages), and (for CSRD) third-party assurance. The
Governance Center's control matrix is designed to make that gap visible
rather than paper over it: a control reads "Partial" specifically when a
requirement is structurally supported but a real data gap remains (most
commonly: no renewable energy contract on file, so market-based Scope 2
can't yet differ from location-based).

## Data quality tiers (ISO 14064-1 clause 5.2)

| Tier | Meaning |
|---|---|
| `high` | Real instance type resolved to a real vCPU count, AND the region matched a provider-sourced grid factor. |
| `medium` | Either the instance type or the region had to fall back to a documented default/estimate, not both. |
| `low` | Neither the instance type nor a provider-specific region was available (e.g. a generic Kaggle-style dataset upload). |
| `unknown` | Record predates standardized ingestion (no `data_quality` column value recorded). |

## Scope 2 market-based instrument hierarchy

Per the GHG Protocol Scope 2 Guidance, in order of preference:

1. Power Purchase Agreement (PPA)
2. Supplier-specific emission factor
3. Unbundled Energy Attribute Certificate (REC / Guarantee of Origin)
4. Residual mix factor (fallback)

Implemented as `MARKET_INSTRUMENT_QUALITY_RANK` in
`compliance/ghg_protocol.py`; `RenewableContractService.find_active_contract()`
picks the best-quality contract on file for a given provider/region.

## Roadmap items that would materially strengthen compliance coverage

See `docs/ROADMAP.md` for full detail. In priority order:

1. A UI for recording renewable energy contracts (the backend/service layer
   already exists — `RenewableContractService` — but no Integrations Hub
   screen calls it yet), closing the Scope 2 market-based gap.
2. Real-time/marginal grid factors (Electricity Maps or WattTime
   integration) instead of annual averages.
3. Per-instance-family embodied carbon (Boavizta API) instead of a single
   reference-server default.
4. A formal Scope 3 category assessment for cloud-related purchased goods
   and services beyond the compute/storage/network boundary this tool
   currently covers.
