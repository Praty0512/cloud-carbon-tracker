"""Governance and reporting workspace page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from compliance.reporting import data_quality_summary, standards_control_checklist
from config import PRODUCT_GLOSSARY
from database.service import (
    ActivityService,
    AuditLogService,
    CarbonResultService,
    DashboardService,
    MembershipService,
    RecommendationService,
    RenewableContractService,
    SavedReportService,
)
from utils.ui import card, empty_state, metric_row, page_header, soft_divider


def show() -> None:
    """Display governance controls and reporting posture."""
    org_id = st.session_state.get("current_org_id")
    user = st.session_state.get("current_user")
    if not org_id:
        st.warning("Select an organization to open governance.")
        return

    snapshot = DashboardService.get_workspace_snapshot(org_id)
    headline = snapshot["headline"]
    recommendations = snapshot["recommendations"]
    reports = snapshot["reports"]
    activity = snapshot["activity"]
    can_write = MembershipService.has_permission(org_id, getattr(user, "id", 0), "reports.write")

    page_header(
        "Governance Center",
        "Manage executive review readiness, optimization backlog, and operating controls in one place. This page "
        "brings together evidence of control health, open optimization work, published reports, and recent "
        "governance activity so finance, sustainability, and platform leaders can review the program consistently.",
        icon="\U0001f6e1️",
    )

    if st.button("\U0001f331 Seed Demo Governance Event", use_container_width=False, disabled=not can_write):
        RecommendationService.create_recommendation(
            org_id=org_id,
            suggestion="Demo action: consolidate low-value batch jobs into scheduled carbon-aware windows.",
            carbon_saving_percent=6.5,
            cost_impact=-950,
            priority="medium",
        )
        SavedReportService.create_report(
            org_id=org_id,
            title="Demo Governance Review",
            report_type="governance",
            summary="Demonstration review package for stakeholder walkthroughs.",
            payload={"demo": True},
            created_by=getattr(user, "id", None),
        )
        ActivityService.log_event(
            org_id=org_id,
            user_id=getattr(user, "id", None),
            event_type="governance",
            title="Demo governance pack created",
            description="A demo review artifact and action were created for walkthroughs.",
        )
        AuditLogService.log(
            org_id=org_id,
            user_id=getattr(user, "id", None),
            action="governance.demo_seeded",
            entity_type="report",
            description="Demo governance report and recommendation seeded.",
        )
        st.rerun()

    metric_row(
        [
            ("Control Coverage", f"{headline['coverage_score']}%", PRODUCT_GLOSSARY["coverage_score"]),
            ("Open Recommendations", str(headline["open_recommendations"]), "Optimization ideas awaiting closure."),
            ("Cost At Risk", f"${headline['cost_at_risk']:,.0f}", "Possible upside from unresolved recommendations."),
            ("Published Reports", str(headline["reports"]), "Reports available in the evidence library."),
        ]
    )

    dq_breakdown = CarbonResultService.get_data_quality_breakdown(org_id)
    dq_summary = data_quality_summary(dq_breakdown)
    market_instruments = RenewableContractService.get_org_contracts(org_id)
    standards_controls = standards_control_checklist(
        headline=headline,
        data_quality=dq_summary,
        market_instrument_count=len(market_instruments),
    )
    controls = [
        {
            "Control": item.control,
            "Standard": item.standard_reference,
            "Status": item.status,
            "Evidence": item.evidence,
        }
        for item in standards_controls
    ]
    # A couple of lightweight operational controls (not tied to a specific
    # external standard) that still matter day-to-day for the team running
    # this workspace, kept alongside the standards-mapped ones above.
    controls.append(
        {
            "Control": "Optimization backlog",
            "Standard": "Internal operating control",
            "Status": "Watch" if headline["open_recommendations"] > 4 else "Healthy",
            "Evidence": f"{headline['open_recommendations']} recommendations awaiting closure",
        }
    )

    left_col, right_col = st.columns([1.05, 0.95])
    with left_col:
        with card("Control Matrix", icon="\U0001f6e1️"):
            st.caption(
                "Each control below cites the real standard clause it maps to (GHG Protocol, ISO 14064-1, "
                "CSRD/ESRS E1, GRI 305) and is graded from this workspace's actual telemetry and data-quality "
                "coverage -- see docs/COMPLIANCE_MAPPING.md for the full writeup."
            )
            st.dataframe(pd.DataFrame(controls), use_container_width=True, hide_index=True)

            if dq_summary["total_records"] > 0:
                st.caption(
                    f"Data quality coverage (ISO 14064-1 clause 5.2): {dq_summary['high_pct']:.0f}% high, "
                    f"{dq_summary['medium_pct']:.0f}% medium, {dq_summary['low_pct']:.0f}% low, "
                    f"{dq_summary['unknown_pct']:.0f}% unrecorded (pre-standardization), across {dq_summary['total_records']} records."
                )

        with card("Action Backlog", icon="\U0001f4cb"):
            st.caption("These recommendations represent optimization opportunities that still need assessment, approval, or delivery.")
            if recommendations:
                backlog_df = pd.DataFrame(recommendations).rename(
                    columns={
                        "suggestion": "Recommendation",
                        "priority": "Priority",
                        "carbon_saving_percent": "Carbon Saving %",
                        "cost_impact": "Cost Impact",
                    }
                )
                st.dataframe(backlog_df, use_container_width=True, hide_index=True)
            else:
                empty_state("No open recommendations. This workspace is clear right now.", icon="✨")

    with right_col:
        with card("Reporting Library", icon="\U0001f4da"):
            st.caption("Saved reports act as the evidence library for operating reviews, leadership updates, and audit preparation.")
            if reports:
                report_df = pd.DataFrame(reports)[["title", "report_type", "summary", "created_at"]]
                report_df.columns = ["Title", "Type", "Summary", "Created At"]
                st.dataframe(report_df, use_container_width=True, hide_index=True)
            else:
                empty_state("No reports have been published yet.", icon="\U0001f4da")

        with card("Recent Governance Activity", icon="\U0001f553"):
            st.caption("Recent activity helps reviewers understand what changed since the last governance checkpoint.")
            if activity:
                for event in activity[:5]:
                    st.markdown(f"**{event['title']}**")
                    st.caption(event["description"])
                    st.caption(str(event["created_at"]))
                    soft_divider()
            else:
                empty_state("No activity recorded yet.", icon="\U0001f553")
