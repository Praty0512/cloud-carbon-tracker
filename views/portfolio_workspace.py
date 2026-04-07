"""Enterprise portfolio workspace page."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from config import PRODUCT_GLOSSARY, get_region_intensity, get_region_label
from database.service import ActivityService, AuditLogService, DashboardService, MembershipService, ProjectService


def show() -> None:
    """Display the portfolio workspace."""
    org_id = st.session_state.get("current_org_id")
    user = st.session_state.get("current_user")
    if not org_id:
        st.warning("Select an organization to open the portfolio workspace.")
        return

    snapshot = DashboardService.get_workspace_snapshot(org_id)
    headline = snapshot["headline"]
    portfolio = snapshot["portfolio"]
    can_write = MembershipService.has_permission(org_id, getattr(user, "id", 0), "actions.write")

    st.header("Portfolio Workspace")
    st.caption("Track project ownership, budget exposure, and carbon performance across your operating estate.")
    st.info(
        "This is the working portfolio view for cloud sustainability operations. "
        "Use it to understand which projects drive emissions, where budgets are concentrated, and which operating regions deserve attention."
    )

    if st.button("Create Demo Portfolio Project", use_container_width=False, disabled=not can_write):
        ProjectService.get_or_create_project(
            org_id=org_id,
            name="Payments Resilience",
            cloud_provider="AWS",
            region="us",
            monthly_budget=18000,
        )
        ActivityService.log_event(
            org_id=org_id,
            user_id=getattr(user, "id", None),
            event_type="project",
            title="Demo portfolio project created",
            description="Payments Resilience was added to illustrate portfolio workflows.",
        )
        AuditLogService.log(
            org_id=org_id,
            user_id=getattr(user, "id", None),
            action="project.demo_created",
            entity_type="project",
            entity_id="Payments Resilience",
            description="Demo portfolio project created.",
        )
        st.rerun()

    top_col1, top_col2, top_col3, top_col4 = st.columns(4)
    top_col1.metric("Tracked Budget", f"${headline['monthly_budget']:,.0f}")
    top_col2.metric("Estimated Spend", f"${headline['estimated_monthly_spend']:,.0f}")
    top_col3.metric("Portfolio Carbon", f"{headline['total_carbon']:,.0f} kg CO2")
    top_col4.metric("Projects At Risk", headline["risk_count"])
    st.caption(
        "Tracked budget is the registered monthly budget across projects. Estimated spend is a simple workspace proxy. "
        "Projects at risk are projects currently contributing disproportionately high carbon."
    )

    if portfolio:
        portfolio_df = pd.DataFrame(portfolio)
        portfolio_df["reporting_region"] = portfolio_df["region"].str.title()
        portfolio_df["operating_region"] = portfolio_df["region"].map(get_region_label)
        portfolio_df["grid_intensity"] = portfolio_df["region"].map(get_region_intensity)
        portfolio_df["budget_utilization_pct"] = (
            portfolio_df["carbon_kg"] / portfolio_df["carbon_kg"].max() * 100
            if portfolio_df["carbon_kg"].max() > 0
            else 0
        )
        portfolio_df["carbon_intensity"] = portfolio_df.apply(
            lambda row: row["carbon_kg"] / row["energy_kwh"] if row["energy_kwh"] else 0.0,
            axis=1,
        )

        left_col, right_col = st.columns([1.15, 0.85])
        with left_col:
            fig = px.bar(
                portfolio_df,
                x="name",
                y="carbon_kg",
                color="cloud_provider",
                text_auto=".1f",
                title="Carbon Exposure By Project",
                labels={"name": "Project", "carbon_kg": "Carbon (kg CO2)"},
            )
            fig.update_layout(xaxis_tickangle=-20)
            st.plotly_chart(fig, use_container_width=True)

        with right_col:
            provider_df = (
                portfolio_df.groupby("cloud_provider", as_index=False)
                .agg({"monthly_budget": "sum", "carbon_kg": "sum"})
                .sort_values("carbon_kg", ascending=False)
            )
            fig = px.bar(
                provider_df,
                x="cloud_provider",
                y="monthly_budget",
                color="carbon_kg",
                title="Budget By Cloud Provider",
                labels={"cloud_provider": "Provider", "monthly_budget": "Budget (USD)", "carbon_kg": "Carbon"},
            )
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("Project Register")
        st.caption(
            f"Primary operating region means: {PRODUCT_GLOSSARY['operating_region']} "
            f"Reporting region means: {PRODUCT_GLOSSARY['reporting_region']}"
        )
        st.dataframe(
            portfolio_df[
                [
                    "name",
                    "cloud_provider",
                    "operating_region",
                    "reporting_region",
                    "grid_intensity",
                    "status",
                    "monthly_budget",
                    "energy_kwh",
                    "carbon_kg",
                    "carbon_intensity",
                    "records",
                ]
            ].rename(
                columns={
                    "name": "Project",
                    "cloud_provider": "Provider",
                    "operating_region": "Primary Operating Region",
                    "reporting_region": "Reporting Region",
                    "grid_intensity": "Grid Intensity (kg CO2/kWh)",
                    "status": "Status",
                    "monthly_budget": "Budget (USD)",
                    "energy_kwh": "Energy (kWh)",
                    "carbon_kg": "Carbon (kg CO2)",
                    "carbon_intensity": "Carbon / kWh",
                    "records": "Tracked Records",
                }
            ),
            use_container_width=True,
        )
    else:
        st.info("No portfolio telemetry yet. Seed the workspace or import a dataset to populate this view.")

    st.subheader("Add Project")
    st.caption("Register a new project so future telemetry, controls, and reports can be tied to a named operating unit.")
    with st.form("create_project_form", clear_on_submit=True):
        form_col1, form_col2, form_col3, form_col4 = st.columns(4)
        name = form_col1.text_input("Project name")
        provider = form_col2.selectbox("Cloud provider", ["AWS", "GCP", "Azure"])
        region = form_col3.selectbox("Primary region", ["us", "europe", "india"])
        budget = form_col4.number_input("Monthly budget", min_value=0.0, value=12000.0, step=500.0)
        submitted = st.form_submit_button("Create Project", use_container_width=True, disabled=not can_write)
        if submitted:
            if not name.strip():
                st.error("Project name is required.")
            else:
                ProjectService.create_project(
                    org_id=org_id,
                    name=name.strip(),
                    cloud_provider=provider,
                    region=region,
                    monthly_budget=float(budget),
                )
                ActivityService.log_event(
                    org_id=org_id,
                    user_id=getattr(user, "id", None),
                    event_type="project",
                    title="Project added",
                    description=f"{name.strip()} was added to the enterprise portfolio.",
                )
                AuditLogService.log(
                    org_id=org_id,
                    user_id=getattr(user, "id", None),
                    action="project.created",
                    entity_type="project",
                    entity_id=name.strip(),
                    description=f"{name.strip()} added to portfolio.",
                )
                st.rerun()
