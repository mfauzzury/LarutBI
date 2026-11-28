"""Register the construction demo database in ChatBI and describe its columns.

Writes straight to the app database, because in lite mode the column-update API
fails without the optional embedding library. Safe to run again.

Run from the project root, after starting the app at least once:
    set -a; source .env; set +a
    PYTHONPATH=backend backend/venv/bin/python data/register_construction.py
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import select

import app.models  # noqa: F401 — registers all models
from app.core.database import AsyncSessionLocal
from app.core.encryption import encrypt
from app.models.datasource import Datasource, DBType
from app.models.schema_column import SchemaColumn
from app.models.schema_table import SchemaTable
from app.models.user import User, UserRole
from app.schema_mgr.introspect import introspect_sqlite

NAME = "Construction Demo"
DB_FILE = Path(__file__).resolve().with_name("demo-construction.sqlite")

TABLES = {
    "projects": "One row per construction project with contract, cost and billing totals",
    "project_account": "Project accounting: forecast profit, work in progress and cash by project",
    "project_cost_summary": "Budget, actual cost and open commitment by project and cost category",
    "project_monthly": "Certified revenue, cost and gross profit by project and month",
    "project_cash_flow": "Cash in and out by project and month",
    "variation_orders": "Changes to contract value",
    "clients": "Project owners who pay the company",
    "progress_claims": "Billing to clients (accounts receivable)",
    "client_receipts": "Money received against progress claims",
    "suppliers": "Material suppliers, subcontractors, plant hire and site services",
    "materials": "Material catalogue with standard prices",
    "purchase_requisitions": "Procurement step 1: requests to buy",
    "purchase_orders": "Procurement step 2: orders and subcontract work orders",
    "purchase_order_lines": "Material quantities and unit prices on purchase orders",
    "goods_receipts": "Procurement step 3: goods or work received",
    "supplier_invoices": "Procurement step 4: supplier bills (accounts payable)",
    "supplier_payments": "Money paid against supplier invoices",
    "overhead_budget_vs_actual": "Head office budget and actual by month and department",
    "accounts": "Chart of accounts",
    "departments": "Head office departments",
    "journal_entries": "General ledger entry headers",
    "journal_lines": "General ledger lines (double entry)",
}

# Column descriptions. All money is in Malaysian Ringgit (MYR).
COLUMNS = {
    "projects.project_code": "Project code such as PRJ-01",
    "projects.contract_value": "Original contract sum in MYR",
    "projects.approved_vo_value": "Total approved variation orders",
    "projects.revised_contract_value": "Contract sum plus approved variation orders",
    "projects.budget_cost": "Budgeted total cost",
    "projects.actual_cost": "Cost incurred to date",
    "projects.open_commitment": "Value ordered but not yet received",
    "projects.certified_to_date": "Total certified by the client (revenue to date)",
    "projects.retention_held": "Retention the client is still holding",
    "projects.percent_complete": "Certified value as a percentage of revised contract, 0-100",
    "projects.status": "Ongoing or Completed",
    "project_account.forecast_final_cost": "Estimated total cost at completion",
    "project_account.forecast_profit": "Revised contract minus forecast final cost",
    "project_account.percent_cost_complete": "Cost to date over forecast final cost, 0-100",
    "project_account.revenue_by_completion": "Revenue earned by percentage of completion (cost method)",
    "project_account.under_billed_amount": "Work done but not yet certified (contract asset, WIP)",
    "project_account.over_billed_amount": "Certified ahead of work done (contract liability)",
    "project_account.retention_receivable": "Retention held by the client",
    "project_account.retention_payable": "Retention held from subcontractors",
    "project_account.net_cash_position": "Cash received minus cash paid; negative means the company is funding the project",
    "project_cost_summary.cost_category": "Materials, Subcontractor, Labour, Plant Hire or Site Overheads",
    "project_cost_summary.remaining_budget": "Budget minus actual minus commitment; negative means overrun",
    "project_monthly.period": "Month as YYYY-MM text",
    "project_cash_flow.period": "Month as YYYY-MM text",
    "variation_orders.status": "Approved, Pending or Rejected",
    "clients.client_type": "Government or Private",
    "progress_claims.certified_amount": "Amount approved by the client, before retention",
    "progress_claims.net_payable": "Certified amount minus retention",
    "progress_claims.outstanding_amount": "Unpaid balance; overdue when due_date is before 2026-10-31",
    "progress_claims.status": "Open, Partially Paid, Paid or Awaiting Certification",
    "suppliers.supplier_type": "Material Supplier, Subcontractor, Plant Hire or Site Overheads",
    "purchase_requisitions.status": "Approved, Pending or Rejected",
    "purchase_orders.promised_delivery_date": "Delivery date promised by the supplier",
    "purchase_orders.status": "Open, Partially Received or Received",
    "purchase_order_lines.unit_price": "Price per unit in MYR; compare over time or between suppliers",
    "goods_receipts.days_late": "Days after the promised delivery date, 0 if on time",
    "supplier_invoices.po_id": "NULL when bought without a purchase order",
    "supplier_invoices.match_status": "Matched, Price Variance (invoice differs from goods received) or No PO",
    "supplier_invoices.outstanding_amount": "Unpaid balance excluding retention; overdue when due_date is before 2026-10-31",
    "supplier_invoices.status": "Open, Partially Paid or Paid",
    "overhead_budget_vs_actual.period": "Month as YYYY-MM text",
    "accounts.account_type": "Asset, Liability, Equity, Revenue or Expense",
    "accounts.account_group": "For example Project Costs, Operating Expenses, Current Assets",
    "journal_lines.project_id": "NULL for head office entries",
}

# General rules for SQL generation, attached to the first column the model reads.
RULES_COLUMN = "accounts.account_code"
RULES = (
    "RULES FOR ALL QUERIES: the database is SQLite, so use strftime and julianday, "
    "never date_trunc, EXTRACT, TO_CHAR or INTERVAL. Write one SELECT statement without "
    "WITH or UNION; use subqueries in FROM instead. Data ends on 2026-10-31: treat that "
    "date as today. Money is MYR. Dates are YYYY-MM-DD text. Prefer the summary tables "
    "project_account, projects, project_cost_summary, project_monthly and project_cash_flow."
)


async def main() -> None:
    if not DB_FILE.exists():
        raise SystemExit(f"{DB_FILE} not found. Run data/seed_construction.py first.")
    async with AsyncSessionLocal() as db:
        admin = (await db.execute(
            select(User).where(User.role == UserRole.superadmin).limit(1))).scalar_one()
        source = (await db.execute(
            select(Datasource).where(Datasource.name == NAME))).scalar_one_or_none()
        if source is None:
            source = Datasource(
                name=NAME, db_type=DBType.sqlite, host="", port=0, database=str(DB_FILE),
                username="", encrypted_password=encrypt(""), readonly_user="",
                readonly_encrypted_password=encrypt(""), created_by=admin.id)
            db.add(source)
            await db.flush()

        described = set()
        for raw in await introspect_sqlite(source.database):
            name = raw["table_name"]
            table = (await db.execute(select(SchemaTable).where(
                SchemaTable.datasource_id == source.id,
                SchemaTable.table_name == name))).scalar_one_or_none()
            if table is None:
                table = SchemaTable(datasource_id=source.id, table_name=name, is_active=True)
                db.add(table)
                await db.flush()
            table.description = TABLES.get(name)
            for raw_column in raw["columns"]:
                key = f"{name}.{raw_column['column_name']}"
                column = (await db.execute(select(SchemaColumn).where(
                    SchemaColumn.table_id == table.id,
                    SchemaColumn.column_name == raw_column["column_name"]))).scalar_one_or_none()
                if column is None:
                    column = SchemaColumn(table_id=table.id, column_name=raw_column["column_name"],
                                          data_type=raw_column["data_type"])
                    db.add(column)
                if key in COLUMNS:
                    column.description = COLUMNS[key]
                    described.add(key)
                if key == RULES_COLUMN:
                    column.notes = RULES
                    described.add("rules")
        await db.commit()

        missing = (set(COLUMNS) | {"rules"}) - described
        if missing:
            raise SystemExit(f"Descriptions with no matching column: {sorted(missing)}")
        print(f"Datasource '{NAME}' ready (id {source.id}), {len(described) - 1} columns described.")


if __name__ == "__main__":
    asyncio.run(main())
