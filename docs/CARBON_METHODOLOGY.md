# Carbon Calculation Methodology

This document explains how Cloud Carbon Tracker turns raw cloud usage into
a carbon estimate, and exactly which numbers are sourced from where. It
replaces the previous state of the project, in which every constant in
`config.py` (`COMPUTE_FACTOR = 0.5`, a region "intensity" table on an
arbitrary 0-1 scale) was invented for the demo rather than derived from any
real dataset.

## Summary

We follow the methodology published by the
[Cloud Carbon Footprint](https://www.cloudcarbonfootprint.org/docs/methodology/)
(CCF) open-source project — the same energy-and-grid-factor approach
independently referenced across the cloud sustainability tooling space —
rather than inventing our own physical model. The formula, at a high
level:

```
Operational carbon = IT energy x PUE x grid carbon intensity
Total carbon        = Operational carbon + Embodied carbon
```

Every number in that formula is implemented in `engine/emission_factors.py`
and composed by `engine/standardized_carbon_engine.py`.

## Energy estimation

### Compute

```
avg_watts_per_vcpu = min_watts + utilization * (max_watts - min_watts)
compute_energy_kwh = avg_watts_per_vcpu * vcpu_count * hours / 1000
```

`min_watts`/`max_watts` are CCF's published per-vCPU wattage curve,
averaged across microarchitectures:

| Provider | Min W | Max W |
|---|---|---|
| AWS | 0.74 | 3.5 |
| GCP | 0.71 | 4.26 |
| Azure | 0.78 | 3.76 |

`utilization` defaults to **50%** when real telemetry isn't available —
the hyperscale datacenter average from the 2016 U.S. Data Center Energy
Usage Report, the same default CCF uses (`DEFAULT_CPU_UTILIZATION` in
`engine/emission_factors.py`).

vCPU count comes from resolving a billing export's instance type
(`resolve_vcpu_count()`) against a compact lookup table of common AWS/GCP/
Azure instance families. An unresolved instance type falls back to a
documented default (2 vCPUs) and is flagged with a lower `data_quality`
tier rather than silently presented as measured.

### Storage, network, memory

```
storage_energy_kwh = (storage_gb / 1000) * wh_per_tb_hour * hours / 1000
network_energy_kwh = network_gb * 0.001
memory_energy_kwh  = memory_gb * 0.000392 * hours / 1000
```

`wh_per_tb_hour` is 1.2 for SSD, 0.65 for HDD (CCF). Network intensity is
0.001 kWh/GB, scoped to inter-datacenter transfer (CDN/end-user egress is
out of scope, per CCF). Memory intensity (0.000392 kW/GB) is the average
of published Crucial/Micron DIMM specs.

### Facility overhead (PUE)

```
facility_energy_kwh = it_energy_kwh * PUE
```

| Provider | PUE |
|---|---|
| AWS | 1.135 |
| GCP | 1.1 |
| Azure | 1.185 |

## Grid carbon intensity

`facility_energy_kwh` is multiplied by a **real, sourced** regional grid
carbon intensity (kg CO2e/kWh), looked up by the actual cloud provider
region code (`data/grid_emissions_aws.json`, `_gcp.json`, `_azure.json`),
compiled from:

- **EPA eGRID** — US regions, by NERC subregion
- **European Environment Agency (EEA)** — EU/UK regions
- **Google** — published per-region factors for GCP
- **EMA Singapore** — Singapore-specific
- **carbonfootprint.com** — other international regions

Source dataset:
[cloud-carbon-footprint/cloud-carbon-coefficients](https://github.com/cloud-carbon-footprint/cloud-carbon-coefficients).
A handful of regions that dataset doesn't cover (Poland, Norway, Spain,
UAE, Saudi Arabia, Israel, Turkey) use a documented IEA/Ember country
average estimate instead — every entry in the JSON files carries a
`source` field so this is never ambiguous, and `engine.emission_factors`
tags results from these regions `estimated_country_average` rather than
`provider_sourced`.

When the specific provider/region isn't in our sourced tables at all
(e.g. a region code we don't recognize), the calculation falls back to
`config.REGION_INTENSITY`, a coarse country-bucket table (also now backed
by real figures, not the old 0-1 scale) and tags the result
`coarse_fallback`. See `engine.emission_factors.get_regional_intensity()`.

**These are annual-average, location-based factors.** They do not capture
hourly/seasonal grid mix variation. A production deployment serious about
carbon-aware scheduling should integrate a real-time provider such as
[Electricity Maps](https://www.electricitymaps.com/) or
[WattTime](https://watttime.org/) — noted as a Phase 2 item in
`docs/ROADMAP.md`.

## Embodied carbon

Optional (`include_embodied=True`), using the Green Software Foundation's
[Software Carbon Intensity](https://sci.greensoftware.foundation/) formula:

```
M = TE * (TR / EL) * (RR / TR)
```

Where `TE` is total embodied emissions for a reference server (we use
1500 kg CO2e — a documented, conservative single reference point rather
than a full per-instance-family Boavizta lookup), `EL` is expected
lifespan (4 years, matching the Dell PowerEdge R740 lifecycle assessment
CCF itself cites), and `RR/TR` is the fraction of a 64-vCPU reference
server's capacity reserved by the workload.

## What changed from the original implementation

| Before | After |
|---|---|
| `COMPUTE_FACTOR = 0.5` kWh/hour flat, any workload | Per-vCPU wattage curve x utilization, per provider |
| Region "intensity" on an arbitrary 0-1 scale | Real kg CO2e/kWh from EPA eGRID / EEA / Google / EMA / carbonfootprint.com |
| No provider-specific PUE | AWS 1.135 / GCP 1.1 / Azure 1.185 |
| AWS/GCP CUR ingestion: `vm_hours * 0.42` flat | Instance-type-aware, region-aware standardized engine |
| No Azure billing export support | `normalize_azure_cost_export_dataframe()` |
| No embodied carbon | SCI-spec embodied carbon, opt-in |
| No data quality signal | Every record tagged `high` / `medium` / `low` |

## Validated against real production telemetry

The engine above is now cross-checked against genuine Microsoft Azure
production VM telemetry (2.7M real VMs, 30-day trace) rather than only
unit tests with invented numbers -- see
`data/reference_datasets/README.md` and
`scripts/build_azure_reference_dataset.py`. This produced two concrete
outcomes:

1. It caught a real bug: `data/grid_emissions_{aws,gcp,azure}.json` had
   every provider-sourced region under-reported by **1000x** (the source
   CCF coefficients are in metric tons CO2e/kWh; this project had copied
   them in as if already in kg CO2e/kWh). Fixed across all three files (94
   regions); `tests/test_emission_factors.py` now has a regression test
   bounding every provider-sourced region to a physically plausible
   0.01-1.0 kg CO2e/kWh range.
2. It surfaced a real finding: actual fleet-average CPU utilization across
   those 2.7M VMs is ~15.6% (median 8.2%) -- well below the 50%
   hyperscale-average default this engine (and CCF) falls back to absent
   real telemetry. `utils/demo_data.py` now samples from this real
   empirical distribution (`data/reference_datasets/azure_utilization_profile.json`)
   instead of arbitrary numbers, so demo data in this app reflects a real
   production fleet's statistical shape.

## Known limitations (disclosed, not hidden)

- Annual-average grid factors, not real-time/marginal.
- A single embodied-carbon reference point rather than a full Boavizta
  per-instance-family database.
- Storage/network energy intensity in the manual calculator treats a
  single GB snapshot as a one-month allocation (730 hours) for UX
  simplicity — see the docstring in `engine/carbon_engine.py`.
- 8 of ~30 country/region entries use an estimated national average
  rather than a provider-specific published figure (flagged in the JSON
  source files).
