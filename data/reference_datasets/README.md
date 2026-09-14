# Reference dataset: Microsoft Azure Public Dataset (v2)

This directory holds a real-world benchmark derived from genuine Microsoft
Azure production VM telemetry, used to validate the forecasting pipeline
(`ml/forecasting.py`) against real data and to ground demo/onboarding data
in real statistics instead of invented numbers.

## Source

**Azure/AzurePublicDataset**, v2 "vmtable" trace, published by the Microsoft
Azure Compute team:
https://github.com/Azure/AzurePublicDataset/blob/master/AzurePublicDatasetV2.md

- **2,695,548 real VMs** (after dropping ~2k malformed rows out of ~2.7M)
- A genuine, continuous **30-day** trace window on production infrastructure
- Per VM: creation/deletion timestamp (seconds into the trace), max/average/
  P95 CPU utilization over the VM's lifetime, workload category, and
  Microsoft's own virtual-core-count / memory-GB size "buckets"
- VM, subscription, and deployment IDs are salted hashes for tenant privacy
  — this pipeline never uses those columns, only the aggregate telemetry
- No cloud region is published in this trace (anonymization), so the
  derived daily series treats the fleet as a single representative Azure
  region (`East US`) — **documented**, not hidden; see
  `scripts/build_azure_reference_dataset.py`.

The raw file (`trace_data_vmtable_vmtable.csv.gz`, ~418MB) is downloaded to
`_cache/` on first run of the build script and is **git-ignored** — a file
that size does not belong in the repository. Re-run
`python scripts/build_azure_reference_dataset.py` any time to regenerate
everything in this directory from scratch (it re-downloads only if the
cache is missing).

## What's in this directory (committed, small, derived)

- **`azure_fleet_daily_emissions.csv`** — 30 real trace days x
  (active VM count, total vCPU, fleet-average CPU utilization, compute
  energy, facility energy, operational carbon, embodied carbon, total
  carbon). Every emissions figure is produced by the *exact same*
  `engine/emission_factors.py` formulas used everywhere else in the app —
  this is the real-world benchmark `ml/evaluate_on_reference_dataset.py`
  scores the forecasting model against. Calendar dates are a documented
  synthetic anchor (2024-01-01 = trace day 0); Microsoft does not publish
  which real calendar dates the trace covers.
- **`azure_utilization_profile.json`** — empirical percentile statistics
  (CPU utilization, VM lifetime, instance-size mix) computed from the real
  2.7M-VM sample. `utils/demo_data.py` samples from this instead of
  arbitrary numbers.

## A real bug this exercise caught

Cross-checking the fleet-level math above against `engine/emission_factors`
surfaced a genuine unit bug in `data/grid_emissions_{aws,gcp,azure}.json`:
the source values from the `cloud-carbon-coefficients` project are
published in **metric tons** CO2e/kWh, but they had been copied into this
project's JSON files as if already in **kg** CO2e/kWh — every
provider-sourced region was silently under-reporting real emissions by
**1000x** (e.g. `us-east-1` read `0.000415755` instead of the correct
`0.415755`). Fixed in this pass (all three files, 94 regions total); see
each file's `_meta.correction_note` and
`tests/test_emission_factors.py::test_sourced_grid_factors_are_plausible_kg_co2e_per_kwh_not_metric_tons`,
which now guards against this class of regression.

## Key real-world finding

Real average CPU utilization across this 2.7M-VM fleet is **~15.6% (median
8.2%)** — well below the 50% hyperscale-average default
(`DEFAULT_CPU_UTILIZATION`) this app (and CCF itself) falls back to when
real telemetry isn't available. That default remains a reasonable
documented assumption for *when no per-workload utilization is known*, but
this empirical distribution is what now drives realistic demo data, and
it's worth knowing that real fleets often run colder than the industry
default assumes.

## Regenerating

```bash
python scripts/build_azure_reference_dataset.py
```
