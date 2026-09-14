"""Utility for generating demo cloud usage data.

Kept as a thin, backward-compatible wrapper: the actual generation logic
now lives in `utils.demo_data`, which samples CPU utilization and instance
sizing from real Microsoft Azure production telemetry
(`data/reference_datasets/azure_utilization_profile.json`) instead of the
arbitrary `random.randint(50, 200)` VM-hours this module used to produce.
See `utils/demo_data.py` for the full explanation.
"""

from utils.demo_data import generate_realistic_usage


def generate_fake_usage(rows: int = 50, seed: int | None = None):
    """Generate a demo cloud usage dataset, calibrated to real production telemetry."""
    return generate_realistic_usage(rows=rows, seed=seed)
