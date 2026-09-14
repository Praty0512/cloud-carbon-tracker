"""Helpers to normalize external cloud carbon datasets.

Provider-native billing/usage exports (AWS Cost & Usage Report, GCP
BigQuery billing export, Azure Cost Management export) are parsed here and
turned into workspace telemetry rows using the standardized, real
methodology in :mod:`engine.standardized_carbon_engine` -- instance type
(when present) resolves to a real vCPU count, the raw provider region code
is looked up against sourced grid-carbon-intensity tables
(``data/grid_emissions_{aws,gcp,azure}.json``), and provider PUE is
applied. Every normalized row also carries a ``data_quality`` column
(``high`` / ``medium`` / ``low``) recording whether the instance type and
region were actually recognized or had to fall back to a documented
default -- this feeds directly into the compliance data-quality
disclosure (see :mod:`compliance.reporting`).

Previously the AWS/GCP paths multiplied usage-hours by a flat, made-up
kWh-per-hour constant (``vm_hours * 0.42``) with no notion of instance
size, and there was no Azure-specific parser at all -- an "Azure connector"
would silently fall through to the generic, provider-agnostic normalizer.
"""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from config import resolve_region_key
from engine.emission_factors import resolve_vcpu_count
from engine.standardized_carbon_engine import calculate_standardized_emissions


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

# Azure ARM region names (compact, lowercase, no spaces -- what Cost
# Management exports actually contain in ResourceLocation) mapped to the
# display names used as keys in data/grid_emissions_azure.json.
AZURE_REGION_ALIAS: dict[str, str] = {
    "centralus": "Central US",
    "eastus": "East US",
    "eastus2": "East US 2",
    "eastus3": "East US 3",
    "northcentralus": "North Central US",
    "southcentralus": "South Central US",
    "westcentralus": "West Central US",
    "westus": "West US",
    "westus2": "West US 2",
    "westus3": "West US 3",
    "eastasia": "East Asia",
    "southeastasia": "Southeast Asia",
    "northeurope": "North Europe",
    "westeurope": "West Europe",
    "centralindia": "Central India",
    "southindia": "South India",
    "westindia": "West India",
    "uksouth": "UK South",
    "ukwest": "UK West",
    "francecentral": "France Central",
    "finlandcentral": "Finland Central",
    "germanywestcentral": "Germany West Central",
    "swedencentral": "Sweden Central",
    "polandcentral": "Poland Central",
    "switzerlandnorth": "Switzerland North",
    "norwayeast": "Norway East",
    "spaincentral": "Spain Central",
    "italynorth": "Italy North",
    "uaenorth": "UAE North",
    "israelcentral": "Israel Central",
    "australiaeast": "Australia East",
    "japaneast": "Japan East",
    "koreacentral": "Korea Central",
    "canadacentral": "Canada Central",
    "brazilsouth": "Brazil South",
    "southafricanorth": "South Africa North",
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
        pd.to_datetime(df[mapped["timestamp"]]) if "timestamp" in mapped else pd.Timestamp.now('UTC')
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

    # Generic/Kaggle-style datasets normally carry no instance or provider
    # metadata, so they're tagged "low" by default -- but if the file
    # already carries a data_quality column (e.g. it's a round-tripped
    # export from this app's own realistic demo-data generator, which
    # computes real standardized-engine figures up front), trust and
    # pass that through rather than silently downgrading a real result.
    data_quality_col = _pick_column(columns, ["data_quality", "data_quality_tier"])
    if data_quality_col:
        allowed = {"high", "medium", "low", "unknown"}
        normalized["data_quality"] = (
            df[data_quality_col].astype(str).str.lower().where(lambda s: s.isin(allowed), "low")
        )
    else:
        normalized["data_quality"] = "low"
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


def looks_like_azure_cost_export(df: pd.DataFrame) -> bool:
    """Return whether the dataframe resembles an Azure Cost Management export."""
    columns = {column.lower() for column in df.columns}
    signature_columns = {
        "resourcelocation",
        "metercategory",
        "metersubcategory",
        "metername",
        "consumedservice",
        "pretaxcost",
        "resourceid",
    }
    return len(columns & signature_columns) >= 3


def _best_effort_instance_type(text: object) -> str | None:
    """Normalize a free-text billing column into a string resolve_vcpu_count() can match.

    Azure meter names look like "D4s v5" rather than "standard_d4s_v5"; GCP
    SKU descriptions embed a family name inside a longer sentence. This
    tries the raw text first, then the Azure "standard_<slug>" form, and
    returns whichever one actually resolves -- falling back to the raw text
    (still passed through so ``resolve_vcpu_count`` can apply its documented
    default and flag the row as unmatched, rather than silently dropping
    the value).
    """
    raw = str(text or "").strip()
    if not raw:
        return None
    if resolve_vcpu_count(raw)[1]:
        return raw
    slug = "standard_" + raw.lower().replace(" ", "_")
    if resolve_vcpu_count(slug)[1]:
        return slug
    return raw


def _standardize_rows(
    df: pd.DataFrame,
    *,
    provider: str,
    region_series: pd.Series,
    hours_series: pd.Series,
    instance_series: pd.Series | None,
    cost_series: pd.Series,
) -> pd.DataFrame:
    """Run every row through the standardized CCF-methodology engine.

    Row-wise (not vectorized) on purpose: each row can carry a different
    instance type / region, and billing exports in this project's scale
    (portfolio-level monthly exports, not raw per-second telemetry) are
    small enough that clarity wins over micro-optimizing this loop. A
    future iteration ingesting raw per-resource CUR line items at scale
    should vectorize this by pre-grouping identical (region, instance type)
    combinations.
    """
    energy_kwh: list[float] = []
    carbon_kg: list[float] = []
    data_quality: list[str] = []

    for idx in range(len(df)):
        instance_type = instance_series.iloc[idx] if instance_series is not None else None
        result = calculate_standardized_emissions(
            provider=provider,
            region_code=str(region_series.iloc[idx]),
            instance_type=_best_effort_instance_type(instance_type),
            hours=float(hours_series.iloc[idx]) if pd.notna(hours_series.iloc[idx]) else 0.0,
            include_embodied=False,
        )
        energy_kwh.append(result.energy_kwh)
        carbon_kg.append(result.total_carbon_kg)
        data_quality.append(result.data_quality)

    df = df.copy()
    df["energy_kwh"] = energy_kwh
    df["carbon"] = carbon_kg
    df["data_quality"] = data_quality
    return df


def normalize_aws_cur_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize AWS Cost & Usage Report (CUR) columns into workspace telemetry shape."""
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
    instance_type_col = next(
        (column for column in df.columns if column.lower() in {"product/instancetype", "lineitem/usagetype"}),
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
        pd.to_datetime(df[timestamp_col], errors="coerce").fillna(pd.Timestamp.now('UTC'))
        if timestamp_col
        else pd.Timestamp.now('UTC')
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

    instance_series = df[instance_type_col].astype(str) if instance_type_col else None
    normalized = _standardize_rows(
        normalized,
        provider="AWS",
        region_series=raw_region,
        hours_series=normalized["vm_hours"],
        instance_series=instance_series,
        cost_series=normalized["cost"],
    )
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
    # GCP billing exports typically describe the machine type in the SKU
    # description (e.g. "N2 Predefined Instance Core running in Americas")
    # rather than a clean instance-type field -- treat sku/service
    # description as a best-effort text source for vCPU resolution.
    sku_col = next(
        (column for column in df.columns if column.lower() in {"sku.description", "resource.name"}),
        None,
    )

    normalized["timestamp"] = (
        pd.to_datetime(df[timestamp_col], errors="coerce").fillna(pd.Timestamp.now('UTC'))
        if timestamp_col
        else pd.Timestamp.now('UTC')
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

    instance_series = df[sku_col].astype(str) if sku_col else None
    normalized = _standardize_rows(
        normalized,
        provider="GCP",
        region_series=raw_region,
        hours_series=normalized["vm_hours"],
        instance_series=instance_series,
        cost_series=normalized["cost"],
    )
    return normalized


def normalize_azure_cost_export_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize an Azure Cost Management (EA/MCA) usage export into workspace telemetry shape.

    This provider was previously unsupported -- an Azure connector would
    silently fall through to the generic Kaggle-style normalizer, which has
    no notion of Azure region codes, meter categories, or VM sizes, so
    "multi-cloud support" for Azure was aspirational rather than real. This
    function recognizes the standard Cost Management export column set
    (``ResourceLocation``, ``MeterCategory``, ``MeterName``,
    ``UsageQuantity``/``Quantity``, ``PreTaxCost``/``CostInBillingCurrency``).
    """
    columns = {column.lower(): column for column in df.columns}

    def col(*names: str) -> str | None:
        for name in names:
            if name in columns:
                return columns[name]
        return None

    timestamp_col = col("date", "usagedatetime", "usagedate")
    region_col = col("resourcelocation", "meterregion")
    project_col = col("resourcegroup", "subscriptionname", "subscriptionid")
    service_col = col("metercategory", "consumedservice")
    metername_col = col("metername")
    additionalinfo_col = col("additionalinfo")
    usage_col = col("usagequantity", "quantity")
    cost_col = col("pretaxcost", "costinbillingcurrency", "cost")

    normalized = pd.DataFrame()
    normalized["timestamp"] = (
        pd.to_datetime(df[timestamp_col], errors="coerce").fillna(pd.Timestamp.now('UTC'))
        if timestamp_col
        else pd.Timestamp.now('UTC')
    )

    raw_region_compact = (
        df[region_col].astype(str).str.strip().str.lower().str.replace(" ", "", regex=False)
        if region_col
        else pd.Series(["eastus"] * len(df))
    )
    azure_display_region = raw_region_compact.map(lambda code: AZURE_REGION_ALIAS.get(code, "East US"))
    normalized["source_region"] = azure_display_region
    normalized["region"] = azure_display_region.map(map_region_to_app_region)
    normalized["region_key"] = azure_display_region.map(resolve_region_key)
    normalized["project"] = df[project_col].fillna("azure-cost-export").astype(str) if project_col else "azure-cost-export"
    normalized["service"] = df[service_col].fillna("Azure").astype(str) if service_col else "Azure"
    normalized["vm_hours"] = pd.to_numeric(df[usage_col], errors="coerce").fillna(0.0) if usage_col else 0.0
    normalized["storage_gb"] = 0.0
    normalized["network_gb"] = 0.0
    normalized["cost"] = pd.to_numeric(df[cost_col], errors="coerce").fillna(0.0) if cost_col else 0.0

    instance_series = None
    if metername_col and additionalinfo_col:
        instance_series = df[metername_col].astype(str) + " " + df[additionalinfo_col].astype(str)
    elif metername_col:
        instance_series = df[metername_col].astype(str)
    elif additionalinfo_col:
        instance_series = df[additionalinfo_col].astype(str)

    normalized = _standardize_rows(
        normalized,
        provider="AZURE",
        region_series=azure_display_region,
        hours_series=normalized["vm_hours"],
        instance_series=instance_series,
        cost_series=normalized["cost"],
    )
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
    if provider_name == "AZURE" and looks_like_azure_cost_export(raw_df):
        return normalize_azure_cost_export_dataframe(raw_df)
    if looks_like_aws_cur(raw_df):
        return normalize_aws_cur_dataframe(raw_df)
    if looks_like_gcp_billing_export(raw_df):
        return normalize_gcp_billing_dataframe(raw_df)
    if looks_like_azure_cost_export(raw_df):
        return normalize_azure_cost_export_dataframe(raw_df)
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
