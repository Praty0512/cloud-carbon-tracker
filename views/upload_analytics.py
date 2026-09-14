"""Upload Dataset Analytics page."""

import pandas as pd
import plotly.express as px
import streamlit as st

from config import PRODUCT_GLOSSARY, get_region_intensity, get_region_label
from database.service import ActivityService, AlertService, AuditLogService, IngestionRunService, SavedReportService
from engine.carbon_engine import calculate_carbon
from utils.demo_workspace import build_demo_telemetry
from utils.dataset_adapter import normalize_cloud_carbon_dataframe, summarize_dataset_fit
from utils.ui import card, metric_row, page_header


def show():
    """Display the Upload Dataset Analytics page."""
    page_header(
        "Upload Cloud Usage Dataset",
        "Analyze imported telemetry and optionally persist it into the workspace portfolio. The adapter "
        f"normalizes provider-specific columns into a common telemetry shape. {PRODUCT_GLOSSARY['telemetry']}",
        icon="\U0001f4e5",
    )

    demo_col1, demo_col2 = st.columns([0.28, 0.72])
    with demo_col1:
        if st.button("\U0001f331 Use Demo Dataset", use_container_width=True):
            st.session_state["upload_demo_df"] = build_demo_telemetry()

    file = st.file_uploader("Upload CSV", type=["csv"])

    demo_df = st.session_state.get("upload_demo_df")

    if file is not None or demo_df is not None:
        try:
            if demo_df is not None and file is None:
                raw_df = demo_df.copy()
                fit = {
                    "has_timestamp": True,
                    "has_region": True,
                    "has_energy": True,
                    "has_carbon": True,
                    "has_cost": True,
                }
                df = demo_df.copy()
                source_name = "demo_workspace_telemetry.csv"
            else:
                raw_df = pd.read_csv(file)
                fit = summarize_dataset_fit(raw_df)
                df = normalize_cloud_carbon_dataframe(raw_df)
                source_name = getattr(file, "name", "uploaded.csv")

            if not fit["has_region"]:
                st.error("This file does not include a recognizable region column.")
                return

            if not fit["has_carbon"]:
                df["carbon"] = df.apply(
                    lambda row: calculate_carbon(
                        row["vm_hours"],
                        row["storage_gb"],
                        row["network_gb"],
                        row["region"],
                    )[1],
                    axis=1,
                )

            df["operating_region"] = df["region_key"].map(get_region_label)
            df["reporting_region"] = df["region"].str.title()
            df["grid_intensity"] = df["region_key"].map(get_region_intensity)

            st.caption(
                "Dataset adapter applied. Best fit for Kaggle's Cloud Carbon Emissions tables, "
                "including daily_cost_emissions and daily_emissions."
            )

            with card("Region Mapping Summary", icon="\U0001f5fa️"):
                st.caption(
                    "This table explains how imported provider regions are interpreted. "
                    f"Imported Region is the raw source value. Operational Region means: {PRODUCT_GLOSSARY['operating_region']} "
                    f"Reporting Region means: {PRODUCT_GLOSSARY['reporting_region']}"
                )
                region_summary = (
                    df.groupby(["operating_region", "reporting_region", "source_region", "region_key"], as_index=False)
                    .agg(
                        {
                            "carbon": "sum",
                            "energy_kwh": "sum",
                            "cost": "sum",
                            "grid_intensity": "max",
                        }
                    )
                    .sort_values("carbon", ascending=False)
                )
                region_summary = region_summary.rename(
                    columns={
                        "operating_region": "Operational Region",
                        "reporting_region": "Reporting Region",
                        "source_region": "Imported Region",
                        "region_key": "Region Key",
                        "carbon": "Carbon (kg CO2)",
                        "energy_kwh": "Energy (kWh)",
                        "cost": "Cost (USD)",
                        "grid_intensity": "Grid Intensity (kg CO2/kWh)",
                    }
                )
                st.dataframe(region_summary.head(12), use_container_width=True, hide_index=True)

            with card("Dataset Preview", icon="\U0001f50e"):
                st.caption("Preview the normalized telemetry that downstream analytics, forecasts, and portfolio persistence will use.")
                preview_columns = [
                    "timestamp",
                    "project",
                    "service",
                    "source_region",
                    "operating_region",
                    "reporting_region",
                    "grid_intensity",
                    "energy_kwh",
                    "carbon",
                    "cost",
                ]
                preview_df = df[preview_columns].rename(
                    columns={
                        "timestamp": "Timestamp",
                        "project": "Project",
                        "service": "Service",
                        "source_region": "Imported Region",
                        "operating_region": "Operational Region",
                        "reporting_region": "Reporting Region",
                        "grid_intensity": "Grid Intensity (kg CO2/kWh)",
                        "energy_kwh": "Energy (kWh)",
                        "carbon": "Carbon (kg CO2)",
                        "cost": "Cost (USD)",
                    }
                )
                st.dataframe(preview_df, use_container_width=True, hide_index=True)

            with card("Carbon Emissions by Region", icon="\U0001f4ca"):
                st.caption("The left chart is for leadership rollups, while the right chart highlights the exact operating regions driving emissions.")
                chart_left, chart_right = st.columns(2)
                reporting_region_chart = (
                    df.groupby("reporting_region", as_index=False)["carbon"]
                    .sum()
                    .sort_values("carbon", ascending=False)
                )
                operating_region_chart = (
                    df.groupby("operating_region", as_index=False)["carbon"]
                    .sum()
                    .sort_values("carbon", ascending=False)
                    .head(10)
                )
                fig = px.bar(
                    reporting_region_chart,
                    x="reporting_region",
                    y="carbon",
                    title="Carbon By Reporting Region",
                    labels={"carbon": "Carbon (kg CO2)", "reporting_region": "Reporting Region"},
                )
                fig.update_layout(margin=dict(l=10, r=10, t=48, b=10))
                chart_left.plotly_chart(fig, use_container_width=True)

                fig = px.bar(
                    operating_region_chart,
                    x="operating_region",
                    y="carbon",
                    title="Top Operational Regions By Carbon",
                    labels={"carbon": "Carbon (kg CO2)", "operating_region": "Operational Region"},
                )
                fig.update_layout(xaxis_tickangle=-20, margin=dict(l=10, r=10, t=48, b=10))
                chart_right.plotly_chart(fig, use_container_width=True)

                if "timestamp" in df.columns:
                    trend_df = (
                        df.assign(period=df["timestamp"].dt.floor("D"))
                        .groupby("period", as_index=False)["carbon"]
                        .sum()
                        .rename(columns={"period": "timestamp"})
                    )
                    fig = px.line(
                        trend_df,
                        x="timestamp",
                        y="carbon",
                        title="Emission Trend Over Time",
                        labels={"carbon": "Carbon (kg CO2)"},
                    )
                    fig.update_layout(margin=dict(l=10, r=10, t=48, b=10))
                    st.plotly_chart(fig, use_container_width=True)

            with card("Summary Statistics", icon="\U0001f4c8"):
                st.caption("These metrics summarize the imported file after normalization and any derived carbon calculations.")
                metric_row(
                    [
                        ("Total Carbon", f"{df['carbon'].sum():.2f} kg CO2", ""),
                        ("Average Carbon", f"{df['carbon'].mean():.2f} kg CO2", ""),
                        ("Records", str(len(df)), ""),
                    ]
                )
                metric_row(
                    [
                        ("Has Energy Data", "Yes" if fit["has_energy"] else "No", ""),
                        ("Has Cost Data", "Yes" if fit["has_cost"] else "No", ""),
                        ("Source Columns", str(len(raw_df.columns)), ""),
                    ]
                )
                metric_row(
                    [
                        ("Operational Regions", str(df["region_key"].nunique()), ""),
                        ("Reporting Regions", str(df["region"].nunique()), ""),
                        ("Avg Grid Intensity", f"{df['grid_intensity'].mean():.3f} kg/kWh", ""),
                    ]
                )

            org_id = st.session_state.get("current_org_id")
            user = st.session_state.get("current_user")
            if org_id:
                with card("Persist To Workspace", icon="\U0001f4be"):
                    st.caption(
                        "Persisting creates or updates workspace projects, connected scopes, usage records, carbon records, and ingestion history."
                    )
                    persist_col1, persist_col2, persist_col3 = st.columns(3)
                    provider = persist_col1.selectbox(
                        "Cloud provider",
                        options=["AWS", "GCP", "Azure"],
                        key="upload_provider",
                    )
                    account_name = persist_col2.text_input(
                        "Account name",
                        value=f"{provider} imported telemetry",
                        key="upload_account_name",
                    )
                    account_id = persist_col3.text_input(
                        "Account ID / billing scope",
                        value=f"{provider.lower()}-imported-dataset",
                        key="upload_account_id",
                    )
                    if st.button("\U0001f4be Persist Dataset Into Workspace", use_container_width=True):
                        result = IngestionRunService.persist_normalized_dataset(
                            org_id=org_id,
                            normalized_df=df,
                            source_name=source_name,
                            provider=provider,
                            account_name=account_name.strip() or f"{provider} imported telemetry",
                            account_id=account_id.strip() or f"{provider.lower()}-imported-dataset",
                            created_by=getattr(user, "id", None),
                        )
                        ActivityService.log_event(
                            org_id=org_id,
                            user_id=getattr(user, "id", None),
                            event_type="ingestion",
                            title="Dataset persisted to workspace",
                            description=(
                                f"Imported {result['rows_persisted']} grouped telemetry records from "
                                f"{source_name}."
                            ),
                            metadata_json={"projects": result["projects_created_or_matched"]},
                        )
                        AuditLogService.log(
                            org_id=org_id,
                            user_id=getattr(user, "id", None),
                            action="dataset.persisted",
                            entity_type="ingestion_run",
                            entity_id=str(result["run"]["id"]),
                            description=f"Persisted telemetry from {source_name} into workspace tables.",
                            metadata_json={"rows_persisted": result["rows_persisted"]},
                        )
                        if df["carbon"].sum() > 3000:
                            AlertService.create_alert(
                                org_id=org_id,
                                title="Large telemetry import requires review",
                                description="A high-volume dataset import has materially changed the workspace telemetry baseline.",
                                category="ingestion",
                                severity="medium",
                                metric_value=float(df["carbon"].sum()),
                                threshold_value=3000.0,
                            )
                        st.success(
                            f"Persisted {result['rows_persisted']} grouped records across "
                            f"{len(result['projects_created_or_matched'])} workspace projects."
                        )

                summary = (
                    f"Processed {len(df)} records with {df['carbon'].sum():.2f} kg CO2 total emissions."
                )
                SavedReportService.create_report(
                    org_id=org_id,
                    title="Uploaded Dataset Analysis",
                    report_type="analytics",
                    summary=summary,
                    payload={
                        "records": int(len(df)),
                        "total_carbon": float(df["carbon"].sum()),
                        "average_carbon": float(df["carbon"].mean()),
                    },
                    created_by=getattr(user, "id", None),
                )
                ActivityService.log_event(
                    org_id=org_id,
                    user_id=getattr(user, "id", None),
                    event_type="dataset",
                    title="Usage dataset analyzed",
                    description=summary,
                    metadata_json={"records": int(len(df))},
                )
        except Exception as exc:
            st.error(f"Error processing file: {exc}")
