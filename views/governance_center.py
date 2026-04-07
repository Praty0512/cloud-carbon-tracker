"""Governance and reporting workspace page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config import PRODUCT_GLOSSARY
from database.service import ActivityService, AuditLogService, DashboardService, MembershipService, RecommendationService, SavedReportService


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

    st.header("Governance Center")
    st.caption("Manage executive review readiness, optimization backlog, and operating controls in one place.")
    st.info(
        "This page is for governance and management review. It brings together evidence of control health, open optimization work, "
        "published reports, and recent governance activity so finance, sustainability, and platform leaders can review the program consistently."
    )

    if st.button("Seed Demo Governance Event", use_container_width=False, disabled=not can_write):
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

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Control Coverage", f"{headline['coverage_score']}%")
    col2.metric("Open Recommendations", headline["open_recommendations"])
    col3.metric("Cost At Risk", f"${headline['cost_at_risk']:,.0f}")
    col4.metric("Published Reports", headline["reports"])
    st.caption(
        f"Coverage score means: {PRODUCT_GLOSSARY['coverage_score']} "
        "Cost at risk estimates possible financial upside from unresolved recommendations."
    )

    controls = [
        {
            "Control": "Executive reporting cadence",
            "Status": "Healthy" if reports else "Missing",
            "Evidence": "Recent board or operations report available" if reports else "No recent report saved",
        },
        {
            "Control": "Connected cloud estates",
            "Status": "Healthy" if headline["cloud_accounts"] >= 2 else "Partial",
            "Evidence": f"{headline['cloud_accounts']} registered cloud accounts",
        },
        {
            "Control": "Team accountability",
            "Status": "Healthy" if headline["team_members"] >= 3 else "Partial",
            "Evidence": f"{headline['team_members']} active workspace members",
        },
        {
            "Control": "Optimization backlog",
            "Status": "Watch" if headline["open_recommendations"] > 4 else "Healthy",
            "Evidence": f"{headline['open_recommendations']} recommendations awaiting closure",
        },
    ]

    left_col, right_col = st.columns([1.05, 0.95])
    with left_col:
        st.subheader("Control Matrix")
        st.caption("A plain-language view of the core controls an enterprise cloud sustainability program should maintain.")
        st.dataframe(pd.DataFrame(controls), use_container_width=True)

        st.subheader("Action Backlog")
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
            st.dataframe(backlog_df, use_container_width=True)
        else:
            st.info("No open recommendations. This workspace is clear right now.")

    with right_col:
        st.subheader("Reporting Library")
        st.caption("Saved reports act as the evidence library for operating reviews, leadership updates, and audit preparation.")
        if reports:
            report_df = pd.DataFrame(reports)[["title", "report_type", "summary", "created_at"]]
            report_df.columns = ["Title", "Type", "Summary", "Created At"]
            st.dataframe(report_df, use_container_width=True)
        else:
            st.info("No reports have been published yet.")

        st.subheader("Recent Governance Activity")
        st.caption("Recent activity helps reviewers understand what changed since the last governance checkpoint.")
        if activity:
            for event in activity[:5]:
                st.markdown(f"**{event['title']}**")
                st.caption(event["description"])
                st.caption(str(event["created_at"]))
                st.markdown("---")
        else:
            st.info("No activity recorded yet.")
