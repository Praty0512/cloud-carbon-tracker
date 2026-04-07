"""Region Simulation page."""

import pandas as pd
import plotly.express as px
import streamlit as st

from database.service import ActivityService
from engine.simulation_engine import simulate
from utils.demo_workspace import build_demo_scenario


def show():
    """Display the Region Simulation page."""
    st.header("Scenario Planner")
    st.caption("Model regional tradeoffs across cost and emissions before moving workloads or changing placement policy.")
    st.info(
        "This planner is for comparing placement options before teams make infrastructure changes. "
        "Enter an expected workload profile, then compare how candidate regions differ on carbon and cost so you can make an intentional tradeoff."
    )

    if st.button("Load Demo Scenario", use_container_width=False):
        demo = build_demo_scenario()
        st.session_state["scenario_vm"] = demo["vm"]
        st.session_state["scenario_storage"] = demo["storage"]
        st.session_state["scenario_network"] = demo["network"]

    col1, col2, col3 = st.columns(3)
    with col1:
        vm = st.number_input("VM Hours", value=float(st.session_state.get("scenario_vm", 0.0)), min_value=0.0, key="scenario_vm")
    with col2:
        storage = st.number_input("Storage GB", value=float(st.session_state.get("scenario_storage", 0.0)), min_value=0.0, key="scenario_storage")
    with col3:
        network = st.number_input("Network GB", value=float(st.session_state.get("scenario_network", 0.0)), min_value=0.0, key="scenario_network")
    st.caption(
        "VM Hours approximates compute demand, Storage GB captures persistent storage footprint, and Network GB represents transfer volume."
    )

    if st.button("Run Scenario Analysis", use_container_width=True):
        try:
            df = pd.DataFrame(simulate(vm, storage, network))

            st.subheader("Scenario Results")
            st.caption("Each row represents the same workload evaluated against a different regional operating profile.")
            st.dataframe(df, use_container_width=True)

            fig = px.bar(
                df,
                x="Region",
                y=["Carbon", "Cost"],
                barmode="group",
                title="Regional Cost And Carbon Tradeoffs",
                labels={"value": "Value", "variable": "Metric"},
            )
            st.plotly_chart(fig, use_container_width=True)

            min_carbon_idx = df["Carbon"].idxmin()
            min_cost_idx = df["Cost"].idxmin()

            best_carbon_region = df.loc[min_carbon_idx, "Region"]
            best_cost_region = df.loc[min_cost_idx, "Region"]

            card1, card2 = st.columns(2)
            with card1:
                st.info(
                    f"Lowest carbon region: {best_carbon_region} "
                    f"({df.loc[min_carbon_idx, 'Carbon']} kg CO2)"
                )
            with card2:
                st.info(
                    f"Lowest cost region: {best_cost_region} "
                    f"(${df.loc[min_cost_idx, 'Cost']:.2f})"
                )

            org_id = st.session_state.get("current_org_id")
            user = st.session_state.get("current_user")
            if org_id:
                ActivityService.log_event(
                    org_id=org_id,
                    user_id=getattr(user, "id", None),
                    event_type="simulation",
                    title="Scenario analysis completed",
                    description=(
                        f"Best carbon region: {best_carbon_region}. Best cost region: {best_cost_region}."
                    ),
                    metadata_json={
                        "best_carbon_region": best_carbon_region,
                        "best_cost_region": best_cost_region,
                    },
                )
        except Exception as exc:
            st.error(f"Error running simulation: {exc}")
