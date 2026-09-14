"""Tests for utils.dataset_adapter: real multi-cloud billing export normalization."""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from utils.dataset_adapter import (
    looks_like_aws_cur,
    looks_like_azure_cost_export,
    looks_like_gcp_billing_export,
    normalize_aws_cur_dataframe,
    normalize_azure_cost_export_dataframe,
    normalize_gcp_billing_dataframe,
    read_connector_dataframe,
)


def _aws_cur_sample() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "lineitem/UsageStartDate": ["2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"],
            "product/region": ["us-east-1", "eu-north-1"],
            "product/instanceType": ["m5.xlarge", "m5.xlarge"],
            "lineitem/UsageAmount": [730, 730],
            "lineitem/UnblendedCost": [100, 100],
        }
    )


def test_looks_like_aws_cur_detects_signature_columns():
    assert looks_like_aws_cur(_aws_cur_sample()) is True
    assert looks_like_aws_cur(pd.DataFrame({"foo": [1]})) is False


def test_aws_cur_normalization_uses_real_region_specific_carbon():
    normalized = normalize_aws_cur_dataframe(_aws_cur_sample())
    assert list(normalized["data_quality"]) == ["high", "high"]
    # Sweden (eu-north-1) must show far lower carbon than Virginia (us-east-1) for identical usage.
    us_row, eu_row = normalized.iloc[0], normalized.iloc[1]
    assert us_row["energy_kwh"] == eu_row["energy_kwh"]
    assert eu_row["carbon"] < us_row["carbon"]


def test_gcp_billing_normalization_produces_positive_carbon():
    gcp_df = pd.DataFrame(
        {
            "usage_start_time": ["2026-01-01T00:00:00Z"],
            "location.region": ["asia-south1"],
            "project.id": ["proj-a"],
            "service.description": ["Compute Engine"],
            "sku.description": ["N2 Predefined Instance Core running in APAC"],
            "usage.amount": [730],
            "cost": [80],
        }
    )
    assert looks_like_gcp_billing_export(gcp_df) is True
    normalized = normalize_gcp_billing_dataframe(gcp_df)
    assert normalized.loc[0, "carbon"] > 0
    assert normalized.loc[0, "source_region"] == "asia-south1"


def test_azure_cost_export_is_detected_and_normalized():
    azure_df = pd.DataFrame(
        {
            "Date": ["2026-01-01"],
            "ResourceLocation": ["swedencentral"],
            "MeterCategory": ["Virtual Machines"],
            "MeterName": ["D4s v5"],
            "UsageQuantity": [730],
            "PreTaxCost": [50],
            "ResourceGroup": ["rg-prod"],
        }
    )
    assert looks_like_azure_cost_export(azure_df) is True
    normalized = normalize_azure_cost_export_dataframe(azure_df)
    assert normalized.loc[0, "source_region"] == "Sweden Central"
    assert normalized.loc[0, "data_quality"] == "high"
    assert normalized.loc[0, "carbon"] > 0


def test_read_connector_dataframe_routes_azure_csv_correctly():
    azure_df = pd.DataFrame(
        {
            "Date": ["2026-01-01"],
            "ResourceLocation": ["eastus"],
            "MeterCategory": ["Virtual Machines"],
            "MeterName": ["D4s v5"],
            "UsageQuantity": [100],
            "PreTaxCost": [10],
            "ResourceGroup": ["rg-a"],
        }
    )
    buffer = BytesIO(azure_df.to_csv(index=False).encode())
    normalized = read_connector_dataframe(buffer, provider="Azure")
    assert normalized.loc[0, "source_region"] == "East US"


def test_generic_kaggle_style_dataset_still_normalizes_with_low_confidence():
    from utils.dataset_adapter import normalize_cloud_carbon_dataframe

    generic_df = pd.DataFrame(
        {
            "date": ["2026-01-01"],
            "region": ["us"],
            "carbon_kg_co2": [12.5],
        }
    )
    normalized = normalize_cloud_carbon_dataframe(generic_df)
    assert normalized.loc[0, "carbon"] == 12.5
    assert normalized.loc[0, "data_quality"] == "low"
