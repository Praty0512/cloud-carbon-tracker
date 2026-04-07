"""Team and workspace administration page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from database.service import ActivityService, AuditLogService, MembershipService, OrganizationService, UserService


def show() -> None:
    """Display team members and workspace administration tools."""
    org_id = st.session_state.get("current_org_id")
    user = st.session_state.get("current_user")
    if not org_id:
        st.warning("Select an organization to open team workspace.")
        return

    organization = OrganizationService.get_organization(org_id)
    members = MembershipService.get_org_members(org_id)
    can_admin = MembershipService.has_permission(org_id, getattr(user, "id", 0), "workspace.admin")

    st.header("Team Workspace")
    st.caption("Assign ownership, onboard operators, and keep the workspace aligned with enterprise operating roles.")
    st.info(
        "Use this page to manage who can operate the workspace and what responsibilities they hold. "
        "Roles are intentionally business-oriented so platform, FinOps, sustainability, and admin users can collaborate without sharing the same permissions."
    )

    if st.button("Add Demo Team Pack", use_container_width=False, disabled=not can_admin):
        for email, full_name, role in [
            ("alex.finance@example.com", "Alex Finance", "finops"),
            ("nina.platform@example.com", "Nina Platform", "admin"),
            ("rahul.greenops@example.com", "Rahul GreenOps", "sustainability"),
        ]:
            existing_user = UserService.get_user_by_email(email)
            if not existing_user:
                existing_user = UserService.create_user(
                    email=email,
                    password="securepass123",
                    full_name=full_name,
                )
            MembershipService.add_member(org_id, existing_user.id, role=role)
        ActivityService.log_event(
            org_id=org_id,
            user_id=getattr(user, "id", None),
            event_type="team",
            title="Demo team pack added",
            description="Finance, platform, and sustainability demo roles were added to the workspace.",
        )
        AuditLogService.log(
            org_id=org_id,
            user_id=getattr(user, "id", None),
            action="members.demo_pack_added",
            entity_type="membership",
            description="Demo team pack added to the workspace.",
        )
        st.rerun()

    col1, col2, col3 = st.columns(3)
    col1.metric("Members", len(members))
    col2.metric("Plan", getattr(organization, "plan", "starter").title() if organization else "Starter")
    col3.metric("Owners / Admins", sum(1 for member in members if member["role"] in {"owner", "admin"}))
    st.caption(
        "Owners and admins can manage the workspace. Other roles are meant for operational participation with narrower permissions."
    )

    st.subheader("Workspace Team")
    st.caption("This register is the current operating roster for the workspace.")
    if members:
        member_df = pd.DataFrame(members)[["full_name", "email", "role", "is_active", "created_at"]]
        member_df.columns = ["Name", "Email", "Role", "Active", "Joined"]
        st.dataframe(member_df, use_container_width=True)
    else:
        st.info("No members found in this workspace.")

    st.subheader("Invite Member")
    st.caption("Add a new operator, assign a role, and give them access to the organization workspace.")
    with st.form("invite_member_form", clear_on_submit=True):
        invite_col1, invite_col2, invite_col3 = st.columns(3)
        full_name = invite_col1.text_input("Full name")
        email = invite_col2.text_input("Work email")
        role = invite_col3.selectbox("Role", ["member", "finops", "sustainability", "admin"])
        submitted = st.form_submit_button("Add Member", use_container_width=True, disabled=not can_admin)
        if submitted:
            if not email.strip():
                st.error("Email is required.")
            else:
                existing_user = UserService.get_user_by_email(email.strip())
                if not existing_user:
                    existing_user = UserService.create_user(
                        email=email.strip(),
                        password="securepass123",
                        full_name=full_name.strip() or email.split("@")[0],
                    )
                MembershipService.add_member(org_id, existing_user.id, role=role)
                ActivityService.log_event(
                    org_id=org_id,
                    user_id=getattr(user, "id", None),
                    event_type="team",
                    title="Member added",
                    description=f"{email.strip()} joined the workspace as {role}.",
                )
                AuditLogService.log(
                    org_id=org_id,
                    user_id=getattr(user, "id", None),
                    action="member.added",
                    entity_type="membership",
                    entity_id=email.strip(),
                    description=f"{email.strip()} added with role {role}.",
                )
                st.rerun()
