"""Sustainability Scorecard page."""

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics.scorecard import sustainability_scorecard
from config import PRODUCT_GLOSSARY, get_region_intensity, get_region_label
from database.service import ActivityService, SavedReportService
from engine.carbon_engine import calculate_carbon
from utils.demo_workspace import build_demo_telemetry
from utils.dataset_adapter import normalize_cloud_carbon_dataframe, summarize_dataset_fit
from utils.ui import card, metric_row, page_header


def show():
    """Display the Sustainability Scorecard page."""
    page_header(
        "Executive Scorecards",
        "Turn uploaded telemetry into stakeholder-ready carbon summaries and executive metrics -- an at-a-glance "
        "view of emissions performance, regional distribution, and the overall sustainability posture of a dataset.",
        icon="\U0001f3c6",
    )

    if st.button("\U0001f331 Use Demo Scorecard Dataset", use_container_width=False):
        st.session_state["scorecard_demo_df"] = build_demo_telemetry()

    file = st.file_uploader("Upload Dataset", type=["csv"])

    demo_df = st.session_state.get("scorecard_demo_df")

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
            else:
                raw_df = pd.read_csv(file)
                fit = summarize_dataset_fit(raw_df)
                df = normalize_cloud_carbon_dataframe(raw_df)

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

            scorecard = sustainability_scorecard(df)
            st.caption(
                "The scorecard uses normalized telemetry, so uploaded datasets are first mapped into the workspace model before metrics are calculated."
            )

            metric_row(
                [
                    ("Total Carbon", f"{scorecard['Total Carbon']} kg CO2", "Sum across normalized telemetry."),
                    ("Average Carbon", f"{scorecard['Average Carbon']} kg CO2", "Mean per record."),
                    ("Sustainability Score", str(scorecard["Sustainability Score"]), "Composite scorecard rating."),
                ]
            )

            with card("Region Distribution", icon="\U0001f30d"):
                st.caption(
                    f"This section separates executive region rollups from the exact operating regions behind them. "
                    f"{PRODUCT_GLOSSARY['operating_region']} {PRODUCT_GLOSSARY['reporting_region']}"
                )
                chart_left, chart_right = st.columns(2)
                reporting_region_df = (
                    df.groupby("reporting_region", as_index=False)
                    .agg({"carbon": "sum"})
                    .sort_values("carbon", ascending=False)
                )
                fig = px.pie(
                    reporting_region_df,
                    names="reporting_region",
                    values="carbon",
                    title="Carbon By Reporting Region",
                )
                fig.update_layout(margin=dict(l=10, r=10, t=48, b=10))
                chart_left.plotly_chart(fig, use_container_width=True)

                operating_region_df = (
                    df.groupby("operating_region", as_index=False)
                    .agg({"carbon": "sum"})
                    .sort_values("carbon", ascending=False)
                    .head(8)
                )
                fig = px.bar(
                    operating_region_df,
                    x="operating_region",
                    y="carbon",
                    title="Top Operational Regions",
                    labels={"operating_region": "Operational Region", "carbon": "Carbon (kg CO2)"},
                )
                fig.update_layout(xaxis_tickangle=-20, margin=dict(l=10, r=10, t=48, b=10))
                chart_right.plotly_chart(fig, use_container_width=True)

            with card("Regional Accountability View", icon="\U0001f4cd"):
                st.caption("Use this table when leaders or operators need to trace a rolled-up region total back to the source telemetry geography.")
                region_register = (
                    df.groupby(["operating_region", "reporting_region", "source_region", "region_key"], as_index=False)
                    .agg({"carbon": "sum", "cost": "sum", "grid_intensity": "max"})
                    .sort_values("carbon", ascending=False)
                    .rename(
                        columns={
                            "operating_region": "Operational Region",
                            "reporting_region": "Reporting Region",
                            "source_region": "Imported Region",
                            "region_key": "Region Key",
                            "carbon": "Carbon (kg CO2)",
                            "cost": "Cost (USD)",
                            "grid_intensity": "Grid Intensity (kg CO2/kWh)",
                        }
                    )
                )
                st.dataframe(region_register.head(12), use_container_width=True, hide_index=True)

            with card("Data Preview", icon="\U0001f50e"):
                st.caption("This preview shows the normalized rows used to build the scorecard.")
                preview_columns = [
                    "timestamp",
                    "project",
                    "service",
                    "source_region",
                    "operating_region",
                    "reporting_region",
                    "grid_intensity",
                    "carbon",
                    "cost",
                ]
                st.dataframe(
                    df[preview_columns].rename(
                        columns={
                            "timestamp": "Timestamp",
                            "project": "Project",
                            "service": "Service",
                            "source_region": "Imported Region",
                            "operating_region": "Operational Region",
                            "reporting_region": "Reporting Region",
                            "grid_intensity": "Grid Intensity (kg CO2/kWh)",
                            "carbon": "Carbon (kg CO2)",
                            "cost": "Cost (USD)",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            org_id = st.session_state.get("current_org_id")
            user = st.session_state.get("current_user")
            if org_id:
                summary = (
                    f"Sustainability score {scorecard['Sustainability Score']} with "
                    f"{scorecard['Total Carbon']} kg CO2 total emissions."
                )
                SavedReportService.create_report(
                    org_id=org_id,
                    title="Sustainability Scorecard",
                    report_type="scorecard",
                    summary=summary,
                    payload=scorecard,
                    created_by=getattr(user, "id", None),
                )
                ActivityService.log_event(
                    org_id=org_id,
                    user_id=getattr(user, "id", None),
                    event_type="scorecard",
                    title="Scorecard generated",
                    description=summary,
                    metadata_json={"score": scorecard["Sustainability Score"]},
                )
        except Exception as exc:
            st.error(f"Error processing scorecard: {exc}")
