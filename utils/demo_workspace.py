"""Reusable demo helpers for enterprise workspace pages."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import pandas as pd


def build_demo_telemetry(days: int = 60) -> pd.DataFrame:
    """Return a deterministic demo telemetry dataset in normalized workspace shape."""
    rng = random.Random(42)
    base_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
    projects = [
        ("Retail Platform", "checkout-api", "us"),
        ("Customer Analytics", "bigquery-jobs", "europe"),
        ("Model Training Estate", "gpu-training", "india"),
        ("Support Systems", "ticketing", "us"),
    ]

    rows: list[dict[str, object]] = []
    for day_index in range(days):
        timestamp = base_date + timedelta(days=day_index)
        seasonal = 1.0 + 0.16 * ((day_index % 14) / 14.0)
        for project_name, service, region in projects:
            vm_hours = rng.uniform(110, 420) * seasonal
            storage_gb = rng.uniform(300, 1400)
            network_gb = rng.uniform(80, 520)
            energy_kwh = vm_hours * 0.42 + storage_gb * 0.003 + network_gb * 0.0016
            regional_multiplier = {"us": 0.41, "europe": 0.29, "india": 0.48}[region]
            carbon = energy_kwh * regional_multiplier
            cost = vm_hours * 0.085 + storage_gb * 0.002 + network_gb * 0.0045
            rows.append(
                {
                    "timestamp": timestamp,
                    "region": region,
                    "project": project_name,
                    "service": service,
                    "source_region": region,
                    "vm_hours": round(vm_hours, 3),
                    "storage_gb": round(storage_gb, 3),
                    "network_gb": round(network_gb, 3),
                    "energy_kwh": round(energy_kwh, 3),
                    "carbon": round(carbon, 3),
                    "cost": round(cost, 3),
                }
            )
    return pd.DataFrame(rows)


def build_demo_scenario() -> dict[str, float]:
    """Return sensible demo inputs for the scenario planner."""
    return {
        "vm": 4200.0,
        "storage": 12800.0,
        "network": 3400.0,
    }
