"""Helpers to normalize external cloud carbon datasets."""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from config import get_region_intensity, resolve_region_key


ALIAS_GROUPS = {
    "timestamp": ["timestamp", "date", "usage_date", "day", "record_date"],
    "region": ["region", "location", "region_code", "cloud_region"],
    "project": ["project", "project_name", "project_id", "team", "workspace"],
    "service": ["service", "service_name", "cloud_service", "product", "product_code"],
    "vm_hours": ["vm_hours", "compute_hours", "vcpu_hours", "usage_quantity", "usage", "usage_amount"],
    "storage_gb": ["storage_gb", "storage_gb_month", "storage_usage_gb", "storage"],
    "network_gb": ["network_gb", "network_egress_gb", "data_transfer_gb", "network"],
    "energy_kwh": ["energy_kwh", "kwh", "energy_consumption_kwh", "energy"],
    "grid_intensity": ["g_co2_per_kwh", "grid_intensity_g_co2_per_kwh", "carbon_intensity_g_per_kwh"],
    "carbon": [
        "carbon",
        "carbon_kg_co2",
        "carbon_kgco2",
        "co2_kg",
        "emissions_kg_co2",
        "emissions_kgco2",
        "co2_emissions_kg",
        "carbon_emissions_kg",
        "emissions",
    ],
    "cost": ["cost", "cost_usd", "usd_cost", "net_cost", "total_cost"],
}

REGION_GROUPS = {
    "india": [
        "india",
        "asia-south1",
        "asia-south2",
        "mumbai",
        "hyderabad",
        "delhi",
        "ap-south-1",
        "ap-south-2",
    ],
    "us": [
        "us",
        "us-central1",
        "us-east1",
        "us-east4",
        "us-west1",
        "us-west2",
        "us-west3",
        "us-west4",
        "northamerica-northeast1",
        "northamerica-northeast2",
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2",
        "ca-central-1",
    ],
    "europe": [
        "europe",
        "europe-west1",
        "europe-west2",
        "europe-west3",
        "europe-west4",
        "europe-west6",
        "europe-central2",
        "europe-north1",
        "europe-southwest1",
        "eu-west-1",
        "eu-west-2",
        "eu-west-3",
        "eu-central-1",
        "eu-central-2",
        "eu-north-1",
        "london",
        "frankfurt",
        "paris",
        "warsaw",
        "milan",
        "zurich",
    ],
}


def _pick_column(columns: list[str], aliases: list[str]) -> str | None:
    """Return the first matching column for a known alias."""
    normalized = {column.lower(): column for column in columns}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    return None


def map_region_to_app_region(region_value: object) -> str:
    """Map provider-style regions into the app's coarse region buckets."""
    region_text = str(region_value).strip().lower()
    resolved = resolve_region_key(region_text)
    if resolved.startswith("india"):
        return "india"
    if resolved.startswith(("us", "canada", "mexico", "brazil")):
        return "us"
    if resolved.startswith(
        (
            "uk",
            "ireland",
            "germany",
            "netherlands",
            "france",
            "spain",
            "italy",
            "poland",
            "sweden",
            "norway",
            "finland",
            "switzerland",
            "europe",
        )
    ):
        return "europe"
    for target, aliases in REGION_GROUPS.items():
        if region_text in aliases:
            return target
    if region_text.startswith(("asia-", "ap-")):
        return "india"
    if region_text.startswith(("us-", "northamerica-")):
        return "us"
    if region_text.startswith(("europe-", "eu-")):
        return "europe"
    return region_text if region_text in REGION_GROUPS else "us"


def normalize_cloud_carbon_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize Kaggle-style cloud carbon data into the app's expected shape."""
    columns = list(df.columns)
    mapped: dict[str, str] = {}

    for target, aliases in ALIAS_GROUPS.items():
        source = _pick_column(columns, aliases)
        if source:
            mapped[target] = source

    normalized = pd.DataFrame()

    normalized["timestamp"] = (
        pd.to_datetime(df[mapped["timestamp"]]) if "timestamp" in mapped else pd.Timestamp.utcnow()
    )
    raw_region_series = df[mapped["region"]] if "region" in mapped else pd.Series(["us"] * len(df))
    normalized["region"] = raw_region_series.map(map_region_to_app_region)
    normalized["region_key"] = raw_region_series.map(resolve_region_key)
    normalized["project"] = df[mapped["project"]] if "project" in mapped else "unassigned"
    normalized["service"] = df[mapped["service"]] if "service" in mapped else "unknown"
    normalized["source_region"] = raw_region_series.astype(str)
    normalized["cost"] = pd.to_numeric(df[mapped["cost"]], errors="coerce").fillna(0.0) if "cost" in mapped else 0.0

    for metric in ("vm_hours", "storage_gb", "network_gb", "energy_kwh"):
        if metric in mapped:
            normalized[metric] = pd.to_numeric(df[mapped[metric]], errors="coerce").fillna(0.0)
        else:
            normalized[metric] = 0.0

    if "carbon" in mapped:
        normalized["carbon"] = pd.to_numeric(df[mapped["carbon"]], errors="coerce").fillna(0.0)
    elif "energy_kwh" in mapped and "grid_intensity" in mapped:
        energy = pd.to_numeric(df[mapped["energy_kwh"]], errors="coerce").fillna(0.0)
        grid_intensity = pd.to_numeric(df[mapped["grid_intensity"]], errors="coerce").fillna(0.0)
        normalized["carbon"] = (energy * grid_intensity) / 1000.0
    else:
        normalized["carbon"] = 0.0

    # When usage is not split by resource category, keep it in compute hours for analytics continuity.
    if "vm_hours" not in mapped and "energy_kwh" not in mapped and "carbon" in mapped:
        normalized["vm_hours"] = 0.0

    return normalized


def looks_like_aws_cur(df: pd.DataFrame) -> bool:
    """Return whether the dataframe resembles an AWS CUR export."""
    columns = {column.lower() for column in df.columns}
    return any(column.startswith("lineitem/") for column in columns) or "product/region" in columns


def looks_like_gcp_billing_export(df: pd.DataFrame) -> bool:
    """Return whether the dataframe resembles a GCP billing export."""
    columns = {column.lower() for column in df.columns}
    return (
        "usage_start_time" in columns
        or "service.description" in columns
        or "project.id" in columns
        or "location.region" in columns
    )


def normalize_aws_cur_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a subset of common AWS CUR columns into workspace telemetry shape."""
    normalized = pd.DataFrame()

    timestamp_col = next(
        (
            column
            for column in df.columns
            if column.lower() in {"lineitem/usagestartdate", "identity/timeinterval", "bill/billingperiodstartdate"}
        ),
        None,
    )
    region_col = next(
        (column for column in df.columns if column.lower() in {"product/region", "lineitem/availabilityzone"}),
        None,
    )
    project_col = next(
        (
            column
            for column in df.columns
            if column.lower() in {
                "resourcetags/user:project",
                "resourcetags/user:project",
                "lineitem/resourceid",
                "bill/payeraccountname",
            }
        ),
        None,
    )
    service_col = next(
        (
            column
            for column in df.columns
            if column.lower() in {"product/productname", "lineitem/productcode", "product/servicename"}
        ),
        None,
    )
    usage_col = next(
        (
            column
            for column in df.columns
            if column.lower() in {"lineitem/usageamount", "pricing/publicondemandcost", "reservation/unusedquantity"}
        ),
        None,
    )
    cost_col = next(
        (
            column
            for column in df.columns
            if column.lower() in {
                "lineitem/unblendedcost",
                "pricing/publicondemandcost",
                "lineitem/blendedcost",
            }
        ),
        None,
    )

    normalized["timestamp"] = (
        pd.to_datetime(df[timestamp_col], errors="coerce").fillna(pd.Timestamp.utcnow())
        if timestamp_col
        else pd.Timestamp.utcnow()
    )
    raw_region = df[region_col].astype(str) if region_col else pd.Series(["us-east-1"] * len(df))
    normalized["source_region"] = raw_region
    normalized["region"] = raw_region.map(map_region_to_app_region)
    normalized["region_key"] = raw_region.map(resolve_region_key)
    normalized["project"] = df[project_col].fillna("aws-cur-project").astype(str) if project_col else "aws-cur-project"
    normalized["service"] = df[service_col].fillna("AWS").astype(str) if service_col else "AWS"
    normalized["vm_hours"] = pd.to_numeric(df[usage_col], errors="coerce").fillna(0.0) if usage_col else 0.0
    normalized["storage_gb"] = 0.0
    normalized["network_gb"] = 0.0
    normalized["cost"] = pd.to_numeric(df[cost_col], errors="coerce").fillna(0.0) if cost_col else 0.0
    normalized["energy_kwh"] = normalized["vm_hours"] * 0.42
    normalized["carbon"] = normalized["energy_kwh"] * normalized["region_key"].map(get_region_intensity)
    return normalized


def normalize_gcp_billing_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize common GCP billing export columns into workspace telemetry shape."""
    normalized = pd.DataFrame()

    timestamp_col = next(
        (
            column
            for column in df.columns
            if column.lower() in {"usage_start_time", "invoice.month", "export_time"}
        ),
        None,
    )
    region_col = next(
        (
            column
            for column in df.columns
            if column.lower() in {"location.region", "location.location", "resource.global_name"}
        ),
        None,
    )
    project_col = next(
        (
            column
            for column in df.columns
            if column.lower() in {"project.id", "project.name", "project.ancestry_numbers"}
        ),
        None,
    )
    service_col = next(
        (
            column
            for column in df.columns
            if column.lower() in {"service.description", "sku.description", "service.id"}
        ),
        None,
    )
    usage_col = next(
        (
            column
            for column in df.columns
            if column.lower() in {"usage.amount", "cost", "cost_at_list", "credits.amount"}
        ),
        None,
    )
    cost_col = next(
        (
            column
            for column in df.columns
            if column.lower() in {"cost", "cost_at_list", "subtotal"}
        ),
        None,
    )

    normalized["timestamp"] = (
        pd.to_datetime(df[timestamp_col], errors="coerce").fillna(pd.Timestamp.utcnow())
        if timestamp_col
        else pd.Timestamp.utcnow()
    )
    raw_region = df[region_col].fillna("us-central1").astype(str) if region_col else pd.Series(["us-central1"] * len(df))
    normalized["source_region"] = raw_region
    normalized["region"] = raw_region.map(map_region_to_app_region)
    normalized["region_key"] = raw_region.map(resolve_region_key)
    normalized["project"] = df[project_col].fillna("gcp-billing-project").astype(str) if project_col else "gcp-billing-project"
    normalized["service"] = df[service_col].fillna("GCP").astype(str) if service_col else "GCP"
    normalized["vm_hours"] = pd.to_numeric(df[usage_col], errors="coerce").fillna(0.0) if usage_col else 0.0
    normalized["storage_gb"] = 0.0
    normalized["network_gb"] = 0.0
    normalized["cost"] = pd.to_numeric(df[cost_col], errors="coerce").fillna(0.0) if cost_col else 0.0
    normalized["energy_kwh"] = normalized["vm_hours"] * 0.38
    normalized["carbon"] = normalized["energy_kwh"] * normalized["region_key"].map(get_region_intensity)
    return normalized


def read_connector_dataframe(path_or_buffer: object, provider: str | None = None) -> pd.DataFrame:
    """Read a connector source and normalize it when provider-specific patterns are detected."""
    if isinstance(path_or_buffer, (str, bytes, BytesIO)):
        raw_df = pd.read_csv(path_or_buffer)
    else:
        raw_df = pd.read_csv(path_or_buffer)

    provider_name = (provider or "").upper()
    if provider_name == "AWS" and looks_like_aws_cur(raw_df):
        return normalize_aws_cur_dataframe(raw_df)
    if provider_name == "GCP" and looks_like_gcp_billing_export(raw_df):
        return normalize_gcp_billing_dataframe(raw_df)
    if looks_like_aws_cur(raw_df):
        return normalize_aws_cur_dataframe(raw_df)
    if looks_like_gcp_billing_export(raw_df):
        return normalize_gcp_billing_dataframe(raw_df)
    return normalize_cloud_carbon_dataframe(raw_df)


def summarize_dataset_fit(df: pd.DataFrame) -> dict[str, bool]:
    """Describe which major analytics fields were found in the raw dataset."""
    columns = [column.lower() for column in df.columns]
    return {
        "has_timestamp": any(alias in columns for alias in ALIAS_GROUPS["timestamp"]),
        "has_region": any(alias in columns for alias in ALIAS_GROUPS["region"]),
        "has_energy": any(alias in columns for alias in ALIAS_GROUPS["energy_kwh"]),
        "has_carbon": (
            any(alias in columns for alias in ALIAS_GROUPS["carbon"])
            or (
                any(alias in columns for alias in ALIAS_GROUPS["energy_kwh"])
                and any(alias in columns for alias in ALIAS_GROUPS["grid_intensity"])
            )
        ),
        "has_cost": any(alias in columns for alias in ALIAS_GROUPS["cost"]),
    }
