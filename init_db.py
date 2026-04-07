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


def initialize_db_with_sample_data()->None:
    print("Initializing database...")
    init_db()
    print("Database tables created.")

    # --- USER ---
    admin_email="admin@example.com"
    user=UserService.get_user_by_email(admin_email)

    if not user:
        user=UserService.create_user(
            email=admin_email,
            password="securepass123",
            full_name="Admin User"
        )

    print(f"User ready: {user.email} (ID: {user.id})")

    # --- ORGANIZATION ---
    org_name="Northstar Digital"
    orgs=OrganizationService.get_user_organizations(user.id)

    if orgs:
        org=orgs[0]
        OrganizationService.update_organization(
            org.id,
            name=org_name,
            description="Enterprise cloud sustainability and FinOps workspace",
            plan="enterprise"
        )
        org=OrganizationService.get_organization(org.id)
    else:
        org=OrganizationService.create_organization(
            name=org_name,
            owner_id=user.id,
            description="Enterprise cloud sustainability and FinOps workspace",
            plan="enterprise"
        )

    print(f"Organization ready: {org.name} (ID: {org.id})")

    # --- PROJECTS ---
    existing={p["name"] for p in ProjectService.get_org_projects(org.id)}

    projects=[
        ("Retail Platform","AWS","us",24000),
        ("Customer Analytics","GCP","europe",38000),
        ("Model Training Estate","Azure","india",29000),
    ]

    for name,provider,region,budget in projects:
        if name in existing: continue
        ProjectService.create_project(
            org_id=org.id,
            name=name,
            cloud_provider=provider,
            region=region,
            monthly_budget=budget
        )

    # --- CLOUD ACCOUNTS ---
    accounts=CloudAccountService.get_org_cloud_accounts(org.id)
    existing_providers={a.provider for a in accounts}

    if "AWS" not in existing_providers:
        CloudAccountService.create_cloud_account(org.id,"AWS","AWS Production Landing Zone","123456789","us-east-1")

    if "GCP" not in existing_providers:
        CloudAccountService.create_cloud_account(org.id,"GCP","GCP Analytics Hub","northstar-gcp-prod","europe-west4")

    if "Azure" not in existing_providers:
        CloudAccountService.create_cloud_account(org.id,"Azure","Azure AI Platform","azure-ai-subscription","centralindia")

    # --- CONNECTORS ---
    connectors=ConnectorService.get_org_connectors(org.id)
    existing_names={c["connector_name"] for c in connectors}

    connector_specs=[
        ("AWS","AWS CUR Production","AssumeRole / CUR","123456789","us-east-1","Daily"),
        ("GCP","GCP Billing Export","Service account + BigQuery export","northstar-gcp-prod","europe-west4","Daily"),
        ("Azure","Azure Cost Export","App registration + Cost export","azure-ai-subscription","centralindia","Daily"),
    ]

    for p,n,a,e,r,f in connector_specs:
        if n in existing_names: continue
        ConnectorService.create_connector(
            org_id=org.id,
            provider=p,
            connector_name=n,
            auth_mode=a,
            status="connected",
            external_reference=e,
            scope_region=r,
            sync_frequency=f,
            notes="Seeded enterprise connector"
        )

    connectors=ConnectorService.get_org_connectors(org.id)

    # --- MEMBERS ---
    members=MembershipService.get_org_members(org.id)
    existing_emails={m["email"] for m in members}

    member_specs=[
        ("maya.raman@northstar.example","Maya Raman","admin"),
        ("owen.lee@northstar.example","Owen Lee","finops"),
        ("sofia.khan@northstar.example","Sofia Khan","sustainability"),
    ]

    for email,name,role in member_specs:
        if email in existing_emails: continue

        u=UserService.get_user_by_email(email)
        if not u:
            u=UserService.create_user(email,"securepass123",name)

        MembershipService.add_member(org.id,u.id,role=role)

    # --- ACTIVITY ---
    if not ActivityService.get_recent_activity(org.id):
        ActivityService.log_event(org.id,"Enterprise workspace initialized","Baseline workspace seeded","workspace",user.id)
        ActivityService.log_event(org.id,"Cloud accounts connected","AWS, GCP, Azure integrated","integration",user.id)
        ActivityService.log_event(org.id,"Quarterly review scheduled","Governance planning ready","governance",user.id)

    # --- RECOMMENDATIONS ---
    existing={r.suggestion for r in RecommendationService.get_org_recommendations(org.id)}

    recs=[
        ("Reschedule analytics jobs",12.5,-4200,"high"),
        ("Right-size GPU nodes",8.1,-3100,"high"),
        ("Move data to cold storage",4.8,-1900,"medium"),
    ]

    for s,p,c,pr in recs:
        if s in existing: continue
        RecommendationService.create_recommendation(org.id,s,p,c,pr)

    # --- REPORTS ---
    reports=SavedReportService.get_org_reports(org.id,limit=25)
    existing_titles={r["title"] for r in reports}

    report_specs=[
        ("Executive Carbon Review","board","Quarterly executive summary",{"status":"seeded"}),
        ("Platform Operations Digest","operations","Daily ops summary",{"status":"seeded"}),
    ]

    for t,rt,s,p in report_specs:
        if t in existing_titles: continue
        SavedReportService.create_report(org.id,t,rt,s,p,user.id)

    # --- CARBON DATA ---
    projects=ProjectService.get_org_projects(org.id)
    pmap={p["name"]:p for p in projects}

    snap=DashboardService.get_workspace_snapshot(org.id)

    if snap["headline"]["total_carbon"]<=0:
        data=[
            ("Retail Platform","us",6100,2620),
            ("Customer Analytics","europe",8300,2985),
            ("Model Training Estate","india",9600,4120),
        ]

        for n,r,e,c in data:
            p=pmap.get(n)
            CarbonResultService.create_carbon_result(
                org.id,
                p["id"] if p else None,
                e,
                c,
                e*0.68,
                e*0.18,
                e*0.14,
                r
            )

    # --- ALERTS ---
    if not AlertService.get_org_alerts(org.id):
        alerts=AlertService.generate_workspace_alerts(org.id)
        if alerts:
            a=alerts[0]
            ActionItemService.create_action_item(
                org.id,
                a["id"],
                "Validate alert",
                a.get("description"),
                user.id,
                a.get("severity","medium")
            )

    # --- AUDIT ---
    if not AuditLogService.get_org_logs(org.id):
        AuditLogService.log(org.id,"workspace.seeded","organization",entity_id=str(org.id),user_id=user.id)

    # --- JOBS ---
    if not ConnectorJobService.get_org_jobs(org.id):
        aws=next((c for c in connectors if c["provider"]=="AWS"),None)
        if aws:
            ConnectorJobService.queue_sync_job(
                org_id=org.id,
                connector_id=int(aws["id"]),
                trigger_mode="scheduled",
                requested_by=user.id,
                payload={"seeded": True}
            )

    print("Database initialized successfully.")
    print(f"Email: {user.email}")
    print("Password: securepass123")
    print(f"Organization ID: {org.id}")


if __name__=="__main__":
    initialize_db_with_sample_data()