"""Operations center for alerts, actions, and audit visibility."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from database.service import (
    ActionItemService,
    ActivityService,
    AlertService,
    AuditLogService,
    DashboardService,
    MembershipService,
)
from utils.ui import card, empty_state, metric_row, page_header


def show() -> None:
    """Display operations queues and enterprise controls."""
    org_id = st.session_state.get("current_org_id")
    user = st.session_state.get("current_user")
    if not org_id:
        st.warning("Select an organization to open operations center.")
        return

    snapshot = DashboardService.get_workspace_snapshot(org_id)
    alerts = snapshot["alerts"]
    action_items = snapshot["action_items"]
    audit_logs = snapshot["audit_logs"]

    page_header(
        "Operations Center",
        "Triage risks, assign remediation, and review the audit trail for the workspace. Alerts highlight issues "
        "detected from telemetry and forecast activity, action items convert those issues into owned work, and the "
        "audit trail shows who changed what for accountability and review.",
        icon="⚙️",
    )

    can_write = MembershipService.has_permission(org_id, getattr(user, "id", 0), "actions.write")

    metric_row(
        [
            ("Open Alerts", str(snapshot["headline"]["open_alerts"]), "Unresolved risk signals."),
            ("Open Actions", str(snapshot["headline"]["open_actions"]), "Remediation tasks still in progress."),
            ("Audit Events", str(len(audit_logs)), "Latest recorded system and user changes."),
        ]
    )

    control_col1, control_col2 = st.columns(2)
    with control_col1:
        if st.button("\U0001f6a8 Generate Risk Alerts", use_container_width=True, disabled=not can_write):
            created = AlertService.generate_workspace_alerts(org_id)
            AuditLogService.log(
                org_id=org_id,
                user_id=getattr(user, "id", None),
                action="alerts.generated",
                entity_type="alert",
                severity="info",
                description=f"Generated {len(created)} workspace alerts from portfolio telemetry.",
            )
            ActivityService.log_event(
                org_id=org_id,
                user_id=getattr(user, "id", None),
                event_type="operations",
                title="Risk alerts refreshed",
                description=f"{len(created)} alert candidates were evaluated from current portfolio telemetry.",
            )
            st.rerun()
    with control_col2:
        if st.button("✅ Create Action From Top Alert", use_container_width=True, disabled=not can_write or not alerts):
            top_alert = alerts[0]
            due_date = datetime.utcnow() + timedelta(days=7)
            item = ActionItemService.create_action_item(
                org_id=org_id,
                alert_id=top_alert["id"],
                title=f"Investigate: {top_alert['title']}",
                description=top_alert.get("description"),
                owner_user_id=getattr(user, "id", None),
                priority=top_alert.get("severity", "medium"),
                due_date=due_date,
            )
            AuditLogService.log(
                org_id=org_id,
                user_id=getattr(user, "id", None),
                action="action_item.created",
                entity_type="action_item",
                entity_id=str(item["id"]),
                description=f"Action item created from alert {top_alert['id']}.",
            )
            st.rerun()

    left_col, right_col = st.columns([1.05, 0.95])
    with left_col:
        with card("Active Alerts", icon="\U0001f6a8"):
            st.caption("These are the highest-priority workspace signals that need triage or monitoring.")
            if alerts:
                alert_df = pd.DataFrame(alerts)[["title", "category", "severity", "status", "metric_value", "threshold_value", "created_at"]]
                alert_df.columns = ["Title", "Category", "Severity", "Status", "Metric", "Threshold", "Created At"]
                st.dataframe(alert_df, use_container_width=True, hide_index=True)
            else:
                empty_state("No alerts yet. Generate them from current telemetry.", icon="\U0001f6a8")

        with card("Action Queue", icon="✅"):
            st.caption("This queue tracks remediation work, owners, due dates, and operational follow-through.")
            if action_items:
                action_df = pd.DataFrame(action_items)[["title", "priority", "status", "owner_name", "owner_email", "due_date", "created_at"]]
                action_df.columns = ["Title", "Priority", "Status", "Owner", "Owner Email", "Due Date", "Created At"]
                st.dataframe(action_df, use_container_width=True, hide_index=True)
            else:
                empty_state("No action items yet.", icon="✅")

    with right_col:
        with card("Audit Trail", icon="\U0001f4dc"):
            st.caption("Audit entries help compliance, incident review, and executive reporting by preserving a record of workspace actions.")
            if audit_logs:
                audit_df = pd.DataFrame(audit_logs)[["created_at", "action", "entity_type", "severity", "description"]]
                audit_df.columns = ["Time", "Action", "Entity", "Severity", "Description"]
                st.dataframe(audit_df, use_container_width=True, hide_index=True)
            else:
                empty_state("No audit events recorded yet.", icon="\U0001f4dc")
