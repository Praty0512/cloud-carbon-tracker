# Connector Import Paths

Place local provider export files here when testing connector syncs without live cloud credentials.

Suggested examples:

- `data/imports/aws_cur.csv`
- `data/imports/gcp_billing_export.csv`
- `data/imports/azure_cost_export.csv`

Then open **Integrations Hub**, select a connector, set the **Local export file path**, and run **Run File Sync**.

The current sync worker expects CSV files that can be normalized by the dataset adapter.
