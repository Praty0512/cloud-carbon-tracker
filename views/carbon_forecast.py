"""AI forecasting workspace for carbon telemetry."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from database.service import (
    ActionItemService,
    ActivityService,
    AlertService,
    AuditLogService,
    CarbonResultService,
    ForecastModelService,
    MembershipService,
    SavedReportService,
)
from engine.carbon_engine import calculate_carbon
from ml.anomaly_detection import detect_anomalies, summarize_anomalies
from ml.forecasting import available_library_report, build_feature_frame, recursive_forecast
from ml.model_registry import get_or_train
from utils.demo_workspace import build_demo_telemetry
from utils.dataset_adapter import normalize_cloud_carbon_dataframe, summarize_dataset_fit
from utils.ui import card, metric_row, page_header


def _prepare_daily_series(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate normalized telemetry into a daily carbon time series."""
    daily = (
        df.assign(day=pd.to_datetime(df["timestamp"]).dt.floor("D"))
        .groupby("day", as_index=False)
        .agg(
            carbon=("carbon", "sum"),
            energy_kwh=("energy_kwh", "sum"),
            cost=("cost", "sum"),
        )
        .sort_values("day")
        .reset_index(drop=True)
    )
    return daily


def _workspace_history(org_id: int) -> pd.DataFrame:
    """Build a normalized dataframe from persisted workspace carbon history."""
    records = CarbonResultService.get_org_carbon_history(org_id, days=365)
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "timestamp": record.timestamp,
                "carbon": record.carbon_kg_co2,
                "energy_kwh": record.energy_kwh,
                "cost": 0.0,
            }
            for record in records
        ]
    )


def show() -> None:
    """Display the AI forecast studio."""
    page_header(
        "AI Forecast Studio",
        "Train a multi-algorithm forecasting bake-off on persisted or uploaded telemetry to project emissions and "
        "planning scenarios. Useful for planning reviews, optimization prioritization, and budget-risk conversations. "
        "Use workspace telemetry for organization-level forecasting, or upload a dataset to test a separate scenario.",
        icon="\U0001f4c8",
    )

    org_id = st.session_state.get("current_org_id")
    user = st.session_state.get("current_user")
    can_write = MembershipService.has_permission(org_id, getattr(user, "id", 0), "forecast.write") if org_id else False

    source = st.radio(
        "Forecast data source",
        options=["Workspace telemetry", "Upload dataset", "Demo telemetry"],
        horizontal=True,
    )
    st.caption(
        "Workspace telemetry uses previously persisted portfolio history. Upload dataset is useful for one-off analysis. "
        "Demo telemetry is best for walkthroughs."
    )

    normalized_df = pd.DataFrame()
    source_name = "workspace telemetry"

    if source == "Workspace telemetry":
        if not org_id:
            st.warning("Select an organization to forecast from workspace telemetry.")
            return
        normalized_df = _workspace_history(org_id)
        if normalized_df.empty:
            st.info("No persisted telemetry yet. Import a dataset into the workspace first, or use an uploaded file below.")
            return
    else:
        if source == "Demo telemetry":
            normalized_df = build_demo_telemetry(days=90)
            source_name = "demo_telemetry"
        else:
            file = st.file_uploader("Upload CSV for Forecasting", type=["csv"])
            if file is None:
                st.info("Upload a telemetry file to train the forecasting model.")
                return
            raw_df = pd.read_csv(file)
            fit = summarize_dataset_fit(raw_df)
            normalized_df = normalize_cloud_carbon_dataframe(raw_df)
            if not fit["has_carbon"]:
                normalized_df["carbon"] = normalized_df.apply(
                    lambda row: calculate_carbon(
                        row["vm_hours"],
                        row["storage_gb"],
                        row["network_gb"],
                        row["region"],
                    )[1],
                    axis=1,
                )
            source_name = getattr(file, "name", "uploaded.csv")

    if normalized_df.empty or "timestamp" not in normalized_df.columns:
        st.warning("A timestamped carbon series is required for forecasting.")
        return

    daily_df = _prepare_daily_series(normalized_df)
    if len(daily_df) < 10:
        st.warning("At least 10 daily points are needed to train the forecasting model.")
        return

    feature_df = build_feature_frame(daily_df)
    if len(feature_df) < 5:
        st.warning("Not enough lagged history was found after feature engineering.")
        return

    scenario_col1, scenario_col2, scenario_col3 = st.columns(3)
    horizon = scenario_col1.slider("Forecast horizon (days)", min_value=7, max_value=90, value=30, step=1)
    growth_pct = scenario_col2.slider("Expected workload growth %", min_value=-10, max_value=30, value=5, step=1)
    reduction_pct = scenario_col3.slider("Planned optimization reduction %", min_value=0, max_value=30, value=8, step=1)
    st.caption(
        "Expected workload growth increases forecasted demand. Planned optimization reduction reflects actions such as rightsizing, scheduling, or regional rebalancing."
    )

    registry_scope = f"{org_id or 'anon'}__{source_name}"
    model, run, was_cache_hit = get_or_train(
        registry_scope, daily_df, source_description=source_name
    )
    forecast_df = recursive_forecast(
        daily_df=daily_df,
        model=model,
        run=run,
        horizon=horizon,
        growth_pct=float(growth_pct),
        reduction_pct=float(reduction_pct),
    )
    mae, mape = run.cv_mae, run.cv_mape

    st.markdown('<div class="glass-card"><h3>\U0001f3c6 Model Performance</h3>', unsafe_allow_html=True)
    st.caption(
        f"Winner: **{run.model_name.replace('_', ' ').title()}** ({run.library}), "
        f"selected from a {len(run.candidates_tried) or 1}-algorithm bake-off via "
        f"{run.cv_folds}-fold walk-forward cross-validation. "
        "Error metrics below are out-of-sample (computed on held-out folds), not a training-set fit. "
        + ("Loaded from the model registry (training data unchanged since the last fit)." if was_cache_hit else "Freshly trained and persisted to the model registry.")
    )
    metric_row(
        [
            ("Training Days", str(len(daily_df)), ""),
            ("CV MAE", f"{mae:.2f} kg CO2", ""),
            ("CV MAPE", f"{mape:.1f}%", ""),
            ("Projected Horizon Total", f"{forecast_df['carbon'].sum():.0f} kg CO2", ""),
        ]
    )
    st.markdown("</div>", unsafe_allow_html=True)

    if run.candidates_tried:
        with st.expander(f"Model bake-off: {len(run.candidates_tried)} algorithms compared", expanded=False):
            st.caption(
                "Every algorithm family actually installed in this environment is cross-validated with the "
                "exact same walk-forward split on the exact same data; the lowest out-of-sample MAE wins. "
                "See `ml/forecast_models.py` for the full rationale behind each candidate, including why the "
                "LSTM is included even though it's expected to lose at this data scale."
            )
            leaderboard_df = pd.DataFrame(
                [{"Model": name.replace("_", " ").title(), "CV MAE (kg CO2)": mae_value} for name, mae_value in run.candidates_tried.items()]
            ).sort_values("CV MAE (kg CO2)").reset_index(drop=True)
            leaderboard_df.insert(0, "Rank", leaderboard_df.index + 1)
            st.dataframe(leaderboard_df, use_container_width=True, hide_index=True)
            if run.best_params:
                st.caption(f"Winning hyperparameters (tuned via randomized search): `{run.best_params}`")
            libraries = available_library_report()
            missing = [name for name, present in libraries.items() if not present]
            if missing:
                st.caption(
                    f"Not installed in this environment (skipped from the comparison): {', '.join(missing)}. "
                    "See requirements.txt to add them."
                )

    if run.feature_importance:
        with st.expander("Model explainability: which signals drove this forecast"):
            importance_df = pd.DataFrame(
                {"Feature": list(run.feature_importance.keys()), "Relative Importance": list(run.feature_importance.values())}
            )
            st.dataframe(importance_df, use_container_width=True, hide_index=True)

    flagged_history = detect_anomalies(daily_df)
    anomalies = summarize_anomalies(flagged_history)
    if anomalies:
        with st.expander(f"⚠️ {len(anomalies)} anomalous day(s) detected in history", expanded=any(a.severity == "high" for a in anomalies)):
            st.caption("Days where carbon deviated sharply from the recent rolling baseline -- worth investigating before trusting the forecast trend.")
            anomaly_table = pd.DataFrame(
                [
                    {
                        "Date": a.day.strftime("%Y-%m-%d"),
                        "Carbon (kg CO2)": round(a.carbon, 2),
                        "Baseline (kg CO2)": round(a.baseline, 2),
                        "Deviation": f"{a.deviation_pct:+.0f}%",
                        "Severity": a.severity,
                    }
                    for a in anomalies
                ]
            )
            st.dataframe(anomaly_table, use_container_width=True, hide_index=True)

    st.markdown('<div class="glass-card"><h3>\U0001f4c9 Historical vs Forecast</h3>', unsafe_allow_html=True)
    st.caption("The chart shows historical emissions, forecasted emissions, and a simple confidence band around the forecast.")
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=daily_df["day"],
            y=daily_df["carbon"],
            mode="lines+markers",
            name="Historical carbon",
            line=dict(color="#38bdf8", width=2),
        )
    )
    figure.add_trace(
        go.Scatter(
            x=forecast_df["day"],
            y=forecast_df["carbon"],
            mode="lines+markers",
            name="AI forecast",
            line=dict(color="#22c55e", width=3),
        )
    )
    figure.add_trace(
        go.Scatter(
            x=forecast_df["day"],
            y=forecast_df["upper_bound"],
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=forecast_df["day"],
            y=forecast_df["lower_bound"],
            mode="lines",
            fill="tonexty",
            fillcolor="rgba(34, 197, 94, 0.18)",
            line=dict(width=0),
            name="Confidence band",
            hoverinfo="skip",
        )
    )
    figure.update_layout(
        title="Forecasted Portfolio Carbon",
        xaxis_title="Date",
        yaxis_title="Carbon (kg CO2)",
        margin=dict(l=20, r=20, t=55, b=20),
    )
    st.plotly_chart(figure, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    with card("Scenario Summary", icon="\U0001f9ee"):
        st.caption("Use this summary to compare the latest actual performance with the projected future trajectory.")
        band_width = run.residual_quantiles[1] - run.residual_quantiles[0]
        metric_row(
            [
                ("Last Actual Day", f"{daily_df['carbon'].iloc[-1]:.1f} kg CO2", ""),
                (
                    "Forecast Day 30" if horizon >= 30 else f"Forecast Day {horizon}",
                    f"{forecast_df['carbon'].iloc[-1]:.1f} kg CO2",
                    "",
                ),
                ("80% Interval Width", f"{band_width:.2f} kg CO2", ""),
            ]
        )

        forecast_table = forecast_df.copy()
        forecast_table["day"] = forecast_table["day"].dt.strftime("%Y-%m-%d")
        st.dataframe(
            forecast_table.rename(
                columns={
                    "day": "Date",
                    "carbon": "Forecast Carbon (kg CO2)",
                    "lower_bound": "Lower Bound",
                    "upper_bound": "Upper Bound",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    if org_id:
        report_summary = (
            f"Forecasted {forecast_df['carbon'].sum():.0f} kg CO2 over the next {horizon} days "
            f"using {len(daily_df)} days of history from {source_name}."
        )
        if st.button("\U0001f4be Save Forecast To Workspace", use_container_width=True, disabled=not can_write):
            model_run = ForecastModelService.create_model_run(
                org_id=org_id,
                name=f"AI Forecast {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                source_type=source_name,
                training_rows=len(daily_df),
                horizon_days=horizon,
                mae=mae,
                mape=mape,
                residual_std=band_width / 2.56,  # approx std-equivalent from the 80% interval width, for schema continuity
                metadata_json={
                    "growth_pct": growth_pct,
                    "reduction_pct": reduction_pct,
                    "projected_total_carbon": float(forecast_df["carbon"].sum()),
                },
                created_by=getattr(user, "id", None),
            )
            SavedReportService.create_report(
                org_id=org_id,
                title="AI Forecast Outlook",
                report_type="forecast",
                summary=report_summary,
                payload={
                    "source": source_name,
                    "horizon_days": horizon,
                    "mae": mae,
                    "mape": mape,
                    "growth_pct": growth_pct,
                    "reduction_pct": reduction_pct,
                    "projected_total_carbon": float(forecast_df["carbon"].sum()),
                },
                created_by=getattr(user, "id", None),
            )
            ActivityService.log_event(
                org_id=org_id,
                user_id=getattr(user, "id", None),
                event_type="forecast",
                title="AI forecast generated",
                description=report_summary,
                metadata_json={"horizon_days": horizon, "mae": round(mae, 2), "mape": round(mape, 2)},
            )
            AuditLogService.log(
                org_id=org_id,
                user_id=getattr(user, "id", None),
                action="forecast.model_saved",
                entity_type="forecast_model",
                entity_id=str(model_run["id"]),
                description=report_summary,
                metadata_json={"mae": mae, "mape": mape, "horizon_days": horizon},
            )
            if forecast_df["carbon"].sum() > daily_df["carbon"].sum() * 0.35:
                alert = AlertService.create_alert(
                    org_id=org_id,
                    title="Forecast indicates elevated carbon trajectory",
                    description="Projected horizon total suggests sustained emissions pressure over the selected planning window.",
                    category="forecast",
                    severity="medium",
                    metric_value=float(forecast_df["carbon"].sum()),
                    threshold_value=float(daily_df["carbon"].sum() * 0.35),
                    metadata_json={"source": source_name, "horizon_days": horizon},
                )
                ActionItemService.create_action_item(
                    org_id=org_id,
                    alert_id=alert["id"],
                    title="Review forecast-driven optimization plan",
                    description="Validate whether forecasted carbon growth should trigger portfolio changes.",
                    owner_user_id=getattr(user, "id", None),
                    priority="medium",
                )
            st.success("Forecast saved to the workspace reports library.")
