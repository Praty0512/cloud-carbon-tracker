"""Carbon Calculator page."""

import streamlit as st

from analytics.analytics import energy_breakdown
from config import REGIONS
from database.service import ActivityService, CarbonResultService
from engine.carbon_engine import calculate_carbon
from engine.recommendation_engine import get_recommendations


def show():
    """Display the Carbon Calculator page."""
    st.header("Carbon Footprint Calculator")

    col1, col2 = st.columns(2)

    with col1:
        vm = st.number_input("VM Hours", value=0.0, min_value=0.0)
        storage = st.number_input("Storage (GB)", value=0.0, min_value=0.0)

    with col2:
        network = st.number_input("Network (GB)", value=0.0, min_value=0.0)
        region = st.selectbox("Region", REGIONS)

    if st.button("Calculate Carbon", use_container_width=True):
        try:
            energy, carbon, compute, storage_e, network_e = calculate_carbon(
                vm,
                storage,
                network,
                region,
            )

            metric_col1, metric_col2, metric_col3 = st.columns(3)
            with metric_col1:
                st.metric("Energy (kWh)", f"{energy:.2f}")
            with metric_col2:
                st.metric("Carbon (kg CO2)", f"{carbon:.2f}")
            with metric_col3:
                score = max(0, 100 - int(carbon / 2))
                st.metric("Sustainability Score", score)

            st.subheader("Energy Breakdown")
            fig = energy_breakdown(compute, storage_e, network_e)
            st.plotly_chart(fig, use_container_width=True)

            st.subheader("Optimization Suggestions")
            recommendations = get_recommendations(vm, storage, region, carbon)
            if recommendations:
                for recommendation in recommendations:
                    st.info(recommendation)
            else:
                st.success("Your configuration is already optimized.")

            org_id = st.session_state.get("current_org_id")
            user = st.session_state.get("current_user")
            if org_id:
                CarbonResultService.create_carbon_result(
                    org_id=org_id,
                    energy_kwh=energy,
                    carbon_kg_co2=carbon,
                    compute_energy=compute,
                    storage_energy=storage_e,
                    network_energy=network_e,
                    region=region,
                )
                ActivityService.log_event(
                    org_id=org_id,
                    user_id=getattr(user, "id", None),
                    event_type="calculation",
                    title="Carbon calculation completed",
                    description=f"Calculated {carbon:.2f} kg CO2 for a {region} workload scenario.",
                    metadata_json={"region": region, "carbon": carbon},
                )
        except Exception as exc:
            st.error(f"Unexpected error: {exc}")
