"""Initialize the database with sample SaaS data."""

from database.connection import init_db
from database.service import (
    ActionItemService,
    ActivityService,
    AlertService,
    AuditLogService,
    CarbonResultService,
    CloudAccountService,
    ConnectorJobService,
    ConnectorService,
    DashboardService,
    MembershipService,
    OrganizationService,
    ProjectService,
    RecommendationService,
    SavedReportService,
    UserService,
)


def initialize_db_with_sample_data() -> None:
    """Initialize database and create sample data."""
    print("Initializing database...")
    init_db()
    print("Database tables created.")

    existing_user = UserService.get_user_by_email("admin@example.com")
    if existing_user:
        user = existing_user
    else:
        user = UserService.create_user(
            email="admin@example.com",
            password="securepass123",
            full_name="Admin User",
        )
    print(f"User ready: {user.email} (ID: {user.id})")

    organizations = OrganizationService.get_user_organizations(user.id)
    if organizations:
        org = organizations[0]
        OrganizationService.update_organization(
            org.id,
            name="Northstar Digital",
            description="Enterprise cloud sustainability and FinOps workspace",
            plan="enterprise",
        )
        org = OrganizationService.get_organization(org.id)
    else:
        org = OrganizationService.create_organization(
            name="Northstar Digital",
            owner_id=user.id,
            description="Enterprise cloud sustainability and FinOps workspace",
            plan="enterprise",
        )
    print(f"Organization ready: {org.name} (ID: {org.id})")

    project_list = ProjectService.get_org_projects(org.id)
    existing_project_names = {project["name"] for project in project_list}
    seeded_project_specs = [
        ("Retail Platform", "AWS", "us", 24000),
        ("Customer Analytics", "GCP", "europe", 38000),
        ("Model Training Estate", "Azure", "india", 29000),
    ]
    for name, provider, region, monthly_budget in seeded_project_specs:
        if name in existing_project_names:
            continue
        ProjectService.create_project(
            org_id=org.id,
            name=name,
            cloud_provider=provider,
            region=region,
            monthly_budget=monthly_budget,
        )

    cloud_accounts = CloudAccountService.get_org_cloud_accounts(org.id)
    existing_provider_accounts = {account.provider for account in cloud_accounts}
    if "AWS" not in existing_provider_accounts:
        CloudAccountService.create_cloud_account(
            org_id=org.id,
            provider="AWS",
            account_name="AWS Production Landing Zone",
            account_id="123456789",
            region="us-east-1",
        )
    if "GCP" not in existing_provider_accounts:
        CloudAccountService.create_cloud_account(
            org_id=org.id,
            provider="GCP",
            account_name="GCP Analytics Hub",
            account_id="northstar-gcp-prod",
            region="europe-west4",
        )
    if "Azure" not in existing_provider_accounts:
        CloudAccountService.create_cloud_account(
            org_id=org.id,
            provider="Azure",
            account_name="Azure AI Platform",
            account_id="azure-ai-subscription",
            region="centralindia",
        )

    existing_connectors = ConnectorService.get_org_connectors(org.id)
    existing_connector_names = {connector["connector_name"] for connector in existing_connectors}
    connector_specs = [
        ("AWS", "AWS CUR Production", "AssumeRole / CUR", "123456789", "us-east-1", "Daily"),
        ("GCP", "GCP Billing Export", "Service account + BigQuery export", "northstar-gcp-prod", "europe-west4", "Daily"),
        ("Azure", "Azure Cost Export", "App registration + Cost export", "azure-ai-subscription", "centralindia", "Daily"),
    ]
    for provider, name, auth_mode, external_reference, scope_region, sync_frequency in connector_specs:
        if name in existing_connector_names:
            continue
        ConnectorService.create_connector(
            org_id=org.id,
            provider=provider,
            connector_name=name,
            auth_mode=auth_mode,
            status="connected",
            external_reference=external_reference,
            scope_region=scope_region,
            sync_frequency=sync_frequency,
            notes="Seeded enterprise connector",
        )
    existing_connectors = ConnectorService.get_org_connectors(org.id)

    member_specs = [
        ("maya.raman@northstar.example", "Maya Raman", "admin"),
        ("owen.lee@northstar.example", "Owen Lee", "finops"),
        ("sofia.khan@northstar.example", "Sofia Khan", "sustainability"),
    ]
    existing_members = MembershipService.get_org_members(org.id)
    existing_emails = {member["email"] for member in existing_members}
    for email, full_name, role in member_specs:
        if email in existing_emails:
            continue
        member_user = UserService.get_user_by_email(email)
        if not member_user:
            member_user = UserService.create_user(
                email=email,
                password="securepass123",
                full_name=full_name,
            )
        MembershipService.add_member(org.id, member_user.id, role=role)

    recent_activity = ActivityService.get_recent_activity(org.id)
    if not recent_activity:
        ActivityService.log_event(
            org_id=org.id,
            user_id=user.id,
            event_type="workspace",
            title="Enterprise workspace initialized",
            description="Baseline workspace seeded with portfolio, members, and governance assets.",
        )
        ActivityService.log_event(
            org_id=org.id,
            user_id=user.id,
            event_type="integration",
            title="Cloud accounts connected",
            description="AWS, GCP, and Azure estates are registered for portfolio tracking.",
        )
        ActivityService.log_event(
            org_id=org.id,
            user_id=user.id,
            event_type="governance",
            title="Quarterly review scheduled",
            description="Sustainability steering review prepared with executive scorecard inputs.",
        )

    existing_recommendations = RecommendationService.get_org_recommendations(org.id)
    existing_suggestions = {recommendation.suggestion for recommendation in existing_recommendations}
    recommendation_specs = [
        (
            "Reschedule non-critical analytics jobs into lower-intensity European windows to reduce portfolio carbon.",
            12.5,
            -4200,
            "high",
        ),
        (
            "Right-size always-on inference nodes in the AI platform to trim idle GPU spend.",
            8.1,
            -3100,
            "high",
        ),
        (
            "Move archived event data to colder storage tiers and enforce lifecycle retention automatically.",
            4.8,
            -1900,
            "medium",
        ),
    ]
    for suggestion, savings, cost_impact, priority in recommendation_specs:
        if suggestion in existing_suggestions:
            continue
        RecommendationService.create_recommendation(
            org_id=org.id,
            suggestion=suggestion,
            carbon_saving_percent=savings,
            cost_impact=cost_impact,
            priority=priority,
        )

    existing_reports = SavedReportService.get_org_reports(org.id, limit=25)
    existing_titles = {report["title"] for report in existing_reports}
    report_specs = [
        (
            "Executive Carbon Review",
            "board",
            "Quarterly board summary covering portfolio emissions, budget efficiency, and decarbonization initiatives.",
            {"status": "seeded", "audience": "executive"},
        ),
        (
            "Platform Operations Digest",
            "operations",
            "Daily operational summary highlighting risk accounts, budget drift, and forecast pressure.",
            {"status": "seeded", "audience": "platform"},
        ),
    ]
    for title, report_type, summary, payload in report_specs:
        if title in existing_titles:
            continue
        SavedReportService.create_report(
            org_id=org.id,
            title=title,
            report_type=report_type,
            summary=summary,
            payload=payload,
            created_by=user.id,
        )

    if not getattr(org, "id", None):
        raise RuntimeError("Organization initialization failed.")

    seeded_projects = ProjectService.get_org_projects(org.id)
    project_by_name = {project["name"]: project for project in seeded_projects}
    workspace_snapshot = DashboardService.get_workspace_snapshot(org.id)
    if workspace_snapshot["headline"]["total_carbon"] <= 0 or not workspace_snapshot["portfolio"]:
        carbon_specs = [
            ("Retail Platform", "us", 6100, 2620),
            ("Retail Platform", "us", 5400, 2315),
            ("Customer Analytics", "europe", 8300, 2985),
            ("Customer Analytics", "europe", 7900, 2760),
            ("Model Training Estate", "india", 9600, 4120),
            ("Model Training Estate", "india", 10100, 4385),
        ]
        for project_name, region, energy_kwh, carbon_kg in carbon_specs:
            project = project_by_name.get(project_name)
            CarbonResultService.create_carbon_result(
                org_id=org.id,
                project_id=project["id"] if project else None,
                energy_kwh=energy_kwh,
                carbon_kg_co2=carbon_kg,
                compute_energy=energy_kwh * 0.68,
                storage_energy=energy_kwh * 0.18,
                network_energy=energy_kwh * 0.14,
                region=region,
            )

    if not AlertService.get_org_alerts(org.id, limit=5):
        created_alerts = AlertService.generate_workspace_alerts(org.id)
        if created_alerts:
            top_alert = created_alerts[0]
            ActionItemService.create_action_item(
                org_id=org.id,
                alert_id=top_alert["id"],
                title="Validate seeded enterprise alert",
                description=top_alert.get("description"),
                owner_user_id=user.id,
                priority=top_alert.get("severity", "medium"),
            )

    if not AuditLogService.get_org_logs(org.id, limit=5):
        AuditLogService.log(
            org_id=org.id,
            user_id=user.id,
            action="workspace.seeded",
            entity_type="organization",
            entity_id=str(org.id),
            description="Enterprise workspace baseline seeded successfully.",
        )

    if not ConnectorJobService.get_org_jobs(org.id, limit=3):
        aws_connector = next((connector for connector in existing_connectors if connector["provider"] == "AWS"), None)
        if aws_connector:
            ConnectorJobService.queue_sync_job(
                org_id=org.id,
                connector_id=int(aws_connector["id"]),
                trigger_mode="scheduled",
                requested_by=user.id,
                payload={"seeded": True, "purpose": "demo background sync"},
            )

    print("Database initialized successfully.")
    print(f"Email: {user.email}")
    print("Password: securepass123")
    print(f"Organization ID: {org.id}")


if __name__ == "__main__":
    initialize_db_with_sample_data()
