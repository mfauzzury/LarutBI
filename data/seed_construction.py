"""Build data/demo-construction.sqlite: synthetic construction-company data in MYR.

All companies and projects are fictional. The output is the same on every run
(fixed random seed). Covers 1 Nov 2024 to 31 Oct 2026.

Simplifications: no SST or other taxes, revenue is recognised when a progress
claim is certified, and retention is never released within the period. The
percentage-of-completion revenue and work-in-progress figures in project_account
are reporting estimates and are not posted to the ledger.

Patterns planted for testing:
  - PRJ-01 overspends on materials and PRJ-04 on subcontractors.
  - Steel rebar prices rise 18% from March 2026.
  - One material supplier delivers late; another charges 9% more.
  - Some material invoices have no purchase order (mostly on PRJ-03).
  - Some supplier invoices are higher than the value received.
  - One private client pays very late and leaves claims unpaid.

Usage (standard library only):
    python3 data/seed_construction.py
"""
from __future__ import annotations

import math
import random
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).with_name("demo-construction.sqlite")
START = date(2024, 11, 1)
AS_OF = date(2026, 10, 31)  # nothing is recorded after this date

rng = random.Random(20261031)

SCHEMA = """
CREATE TABLE accounts (
    account_code TEXT PRIMARY KEY, account_name TEXT, account_type TEXT, account_group TEXT);
CREATE TABLE departments (department_id INTEGER PRIMARY KEY, department_name TEXT);
CREATE TABLE clients (
    client_id INTEGER PRIMARY KEY, client_name TEXT, client_type TEXT, payment_terms_days INTEGER);
CREATE TABLE projects (
    project_id INTEGER PRIMARY KEY, project_code TEXT, project_name TEXT,
    client_id INTEGER REFERENCES clients, state TEXT, start_date TEXT, planned_end_date TEXT,
    contract_value REAL, approved_vo_value REAL, revised_contract_value REAL,
    budget_cost REAL, actual_cost REAL, open_commitment REAL, certified_to_date REAL,
    received_to_date REAL, retention_held REAL, percent_complete REAL, status TEXT);
CREATE TABLE project_account (
    project_code TEXT, project_name TEXT, status TEXT, revised_contract_value REAL,
    cost_to_date REAL, forecast_final_cost REAL, forecast_profit REAL,
    forecast_margin_percent REAL, percent_cost_complete REAL, revenue_by_completion REAL,
    certified_to_date REAL, under_billed_amount REAL, over_billed_amount REAL,
    retention_receivable REAL, retention_payable REAL, cash_received REAL, cash_paid REAL,
    net_cash_position REAL);
CREATE TABLE project_cash_flow (
    period TEXT, project_code TEXT, project_name TEXT, cash_in REAL, cash_out REAL,
    net_cash REAL, cumulative_net_cash REAL);
CREATE TABLE variation_orders (
    vo_id INTEGER PRIMARY KEY, vo_no TEXT, project_id INTEGER REFERENCES projects,
    vo_date TEXT, description TEXT, amount REAL, status TEXT);
CREATE TABLE project_cost_summary (
    project_code TEXT, project_name TEXT, cost_category TEXT, budget_amount REAL,
    actual_amount REAL, open_commitment REAL, remaining_budget REAL);
CREATE TABLE project_monthly (
    period TEXT, project_code TEXT, project_name TEXT, revenue_amount REAL,
    cost_amount REAL, gross_profit REAL);
CREATE TABLE progress_claims (
    claim_id INTEGER PRIMARY KEY, claim_no TEXT, project_id INTEGER REFERENCES projects,
    claim_date TEXT, certified_date TEXT, due_date TEXT, claimed_amount REAL,
    certified_amount REAL, retention_amount REAL, net_payable REAL, paid_amount REAL,
    outstanding_amount REAL, status TEXT);
CREATE TABLE client_receipts (
    receipt_id INTEGER PRIMARY KEY, claim_id INTEGER REFERENCES progress_claims,
    receipt_date TEXT, amount REAL);
CREATE TABLE suppliers (
    supplier_id INTEGER PRIMARY KEY, supplier_name TEXT, supplier_type TEXT,
    payment_terms_days INTEGER);
CREATE TABLE materials (
    material_id INTEGER PRIMARY KEY, material_name TEXT, unit TEXT, standard_price REAL);
CREATE TABLE purchase_requisitions (
    pr_id INTEGER PRIMARY KEY, pr_no TEXT, project_id INTEGER REFERENCES projects,
    pr_date TEXT, cost_category TEXT, estimated_amount REAL, approved_date TEXT, status TEXT);
CREATE TABLE purchase_orders (
    po_id INTEGER PRIMARY KEY, po_no TEXT, pr_id INTEGER REFERENCES purchase_requisitions,
    project_id INTEGER REFERENCES projects, supplier_id INTEGER REFERENCES suppliers,
    po_date TEXT, promised_delivery_date TEXT, cost_category TEXT, total_amount REAL,
    received_amount REAL, status TEXT);
CREATE TABLE purchase_order_lines (
    po_line_id INTEGER PRIMARY KEY, po_id INTEGER REFERENCES purchase_orders,
    material_id INTEGER REFERENCES materials, quantity REAL, unit_price REAL, line_amount REAL);
CREATE TABLE goods_receipts (
    grn_id INTEGER PRIMARY KEY, grn_no TEXT, po_id INTEGER REFERENCES purchase_orders,
    received_date TEXT, received_amount REAL, days_late INTEGER);
CREATE TABLE supplier_invoices (
    invoice_id INTEGER PRIMARY KEY, invoice_no TEXT, supplier_id INTEGER REFERENCES suppliers,
    project_id INTEGER REFERENCES projects, po_id INTEGER REFERENCES purchase_orders,
    grn_id INTEGER REFERENCES goods_receipts, invoice_date TEXT, due_date TEXT,
    cost_category TEXT, amount REAL, retention_amount REAL, net_payable REAL,
    paid_amount REAL, outstanding_amount REAL, match_status TEXT, status TEXT);
CREATE TABLE supplier_payments (
    payment_id INTEGER PRIMARY KEY, invoice_id INTEGER REFERENCES supplier_invoices,
    payment_date TEXT, amount REAL);
CREATE TABLE overhead_budget_vs_actual (
    period TEXT, department_name TEXT, account_name TEXT, budget_amount REAL, actual_amount REAL);
CREATE TABLE journal_entries (
    entry_id INTEGER PRIMARY KEY, entry_date TEXT, period TEXT, source TEXT,
    reference TEXT, description TEXT);
CREATE TABLE journal_lines (
    line_id INTEGER PRIMARY KEY, entry_id INTEGER REFERENCES journal_entries,
    account_code TEXT REFERENCES accounts, project_id INTEGER REFERENCES projects,
    department_id INTEGER REFERENCES departments, debit REAL, credit REAL);
"""

ACCOUNTS = [
    ("1000", "Bank", "Asset", "Current Assets"),
    ("1100", "Trade Receivables", "Asset", "Current Assets"),
    ("1110", "Retention Receivable", "Asset", "Current Assets"),
    ("1500", "Plant and Equipment", "Asset", "Non-current Assets"),
    ("1510", "Accumulated Depreciation", "Asset", "Non-current Assets"),
    ("2000", "Trade Payables", "Liability", "Current Liabilities"),
    ("2010", "Goods Received Not Invoiced", "Liability", "Current Liabilities"),
    ("2020", "Retention Payable", "Liability", "Current Liabilities"),
    ("2500", "Bank Loan", "Liability", "Non-current Liabilities"),
    ("3000", "Share Capital", "Equity", "Equity"),
    ("3100", "Retained Earnings", "Equity", "Equity"),
    ("4000", "Contract Revenue", "Revenue", "Revenue"),
    ("5000", "Materials", "Expense", "Project Costs"),
    ("5100", "Subcontractors", "Expense", "Project Costs"),
    ("5200", "Site Labour", "Expense", "Project Costs"),
    ("5300", "Plant Hire", "Expense", "Project Costs"),
    ("5400", "Site Overheads", "Expense", "Project Costs"),
    ("6000", "Head Office Salaries", "Expense", "Operating Expenses"),
    ("6100", "Office Rent", "Expense", "Operating Expenses"),
    ("6200", "Utilities", "Expense", "Operating Expenses"),
    ("6300", "Software and IT", "Expense", "Operating Expenses"),
    ("6400", "Professional Fees", "Expense", "Operating Expenses"),
    ("6500", "Depreciation", "Expense", "Operating Expenses"),
    ("6800", "Interest Expense", "Expense", "Finance Costs"),
]

# cost category -> (share of project cost, expense account)
CATEGORIES = {
    "Materials": (0.38, "5000"),
    "Subcontractor": (0.32, "5100"),
    "Labour": (0.14, "5200"),
    "Plant Hire": (0.09, "5300"),
    "Site Overheads": (0.07, "5400"),
}

DEPARTMENTS = [(1, "Management"), (2, "Finance"), (3, "Procurement"),
               (4, "Contracts"), (5, "Human Resources"), (6, "IT")]
HEAD_OFFICE_SALARY = {1: 120_000, 2: 55_000, 3: 48_000, 4: 70_000, 5: 32_000, 6: 28_000}
# account, department, monthly amount
HEAD_OFFICE_COSTS = [("6100", 1, 38_000), ("6200", 1, 9_000), ("6300", 6, 22_000), ("6400", 2, 16_000)]

CLIENTS = [
    (1, "Works Department (Demo Agency)", "Government", 45),
    (2, "State Education Office (Demo)", "Government", 60),
    (3, "Seri Cahaya Development", "Private", 30),
    (4, "Pinggir Bayu Properties", "Private", 30),
    (5, "Gerbang Logistics Park", "Private", 45),
]
SLOW_CLIENT = 4

# code, name, client, state, start, months, contract value, overrun by category
PROJECTS = [
    ("PRJ-01", "Taman Seri Apartments Block A and B", 3, "Selangor", date(2024, 11, 1), 20, 38_000_000, {"Materials": 1.22}),
    ("PRJ-02", "SK Bukit Indah School Extension", 2, "Perak", date(2024, 11, 1), 16, 12_500_000, {}),
    ("PRJ-03", "Gerbang Warehouse Phase 1", 5, "Johor", date(2025, 2, 1), 18, 24_000_000, {}),
    ("PRJ-04", "Jalan Sungai Drainage Upgrade", 1, "Kedah", date(2025, 3, 1), 18, 16_800_000, {"Subcontractor": 1.24}),
    ("PRJ-05", "Pinggir Bayu Shop Offices", 4, "Penang", date(2025, 5, 1), 20, 21_000_000, {}),
    ("PRJ-06", "District Health Clinic", 1, "Pahang", date(2025, 8, 1), 22, 18_500_000, {}),
    ("PRJ-07", "Seri Cahaya Condominium Tower", 3, "Kuala Lumpur", date(2025, 11, 1), 30, 62_000_000, {}),
    ("PRJ-08", "Gerbang Warehouse Phase 2", 5, "Johor", date(2026, 3, 1), 18, 27_500_000, {}),
]

MATERIALS = [
    (1, "Ready-mix Concrete G30", "m3", 285), (2, "Steel Rebar", "tonne", 2_950),
    (3, "Cement 50kg", "bag", 22), (4, "River Sand", "m3", 58),
    (5, "Clay Bricks", "1000 pcs", 460), (6, "Formwork Plywood", "sheet", 78),
    (7, "Metal Roofing Sheet", "m2", 39), (8, "Electrical Cable", "metre", 7),
    (9, "PVC Pipe", "length", 29), (10, "Floor Tiles", "m2", 46),
]
# share of material spend per material, in the order above
MATERIAL_WEIGHTS = [26, 28, 9, 5, 7, 6, 6, 5, 3, 5]

# name, materials supplied, price factor, usual delay range in days
MATERIAL_SUPPLIERS = [
    ("Kukuh Concrete Supply", [1, 3, 4], 1.00, (-1, 3)),
    ("Batu Jaya Readymix", [1, 4], 1.09, (-1, 2)),
    ("Waja Steel Trading", [2], 1.00, (-1, 4)),
    ("Besi Utama Metals", [2, 7], 1.02, (9, 25)),
    ("Binaan Hardware Centre", [3, 5, 6, 9], 1.01, (-2, 3)),
    ("Bata Mas Industries", [5, 10], 0.98, (0, 5)),
    ("Papan Kayu Supplies", [6], 0.99, (0, 4)),
    ("Atap Prima Roofing Supply", [7], 1.00, (0, 5)),
    ("Elektrik Sinar Wholesale", [8, 9], 1.00, (-2, 3)),
    ("Jubin Cantik Trading", [10], 1.02, (0, 6)),
]
SERVICE_SUPPLIERS = {
    "Subcontractor": ["Cerucuk Piling Works", "Mekanikal Bestari M and E", "Struktur Padu Builders",
                      "Kemas Painting Services", "Aluminium Wira Contractor", "Longkang Pro Civil Works"],
    "Plant Hire": ["Jentera Sewa Plant Hire", "Kren Tinggi Rentals", "Gali Cepat Machinery"],
    "Site Overheads": ["Kawal Selamat Security", "Bersih Tapak Services", "Kabin Site Rentals"],
}


def cents(ringgit: float) -> int:
    return int(round(ringgit * 100))


def rm(value: int) -> float:
    return value / 100


def add_months(value: date, months: int) -> date:
    total = value.year * 12 + value.month - 1 + months
    return date(total // 12, total % 12 + 1, 1)


def s_curve(fraction: float) -> float:
    """Cumulative progress: slow start, fast middle, slow finish."""
    return (1 - math.cos(math.pi * min(max(fraction, 0), 1))) / 2


class Ledger:
    def __init__(self) -> None:
        self.entries: list[tuple] = []
        self.lines: list[tuple] = []

    def post(self, when: date, source: str, reference: str, description: str,
             lines: list[tuple[str, int, int]], project: int | None = None,
             department: int | None = None) -> None:
        """lines are (account, debit, credit) in sen; zero lines are skipped."""
        assert sum(l[1] for l in lines) == sum(l[2] for l in lines), reference
        entry_id = len(self.entries) + 1
        self.entries.append((entry_id, when.isoformat(), when.strftime("%Y-%m"),
                             source, reference, description))
        for account, debit, credit in lines:
            if debit < 0 or credit < 0:
                debit, credit = max(-credit, 0), max(-debit, 0)
            if debit or credit:
                self.lines.append((len(self.lines) + 1, entry_id, account, project,
                                   department, rm(debit), rm(credit)))


def status_for(due_amount: int, paid: int) -> str:
    if paid >= due_amount:
        return "Paid"
    return "Partially Paid" if paid else "Open"


def main() -> None:
    ledger = Ledger()
    requisitions, orders, order_lines, receipts_in = [], [], [], []
    invoices, payments, claims, receipts, variations = [], [], [], [], []

    ledger.post(START, "Opening", "OB-2024", "Opening balances", [
        ("1000", cents(18_000_000), 0), ("1500", cents(6_000_000), 0),
        ("2500", 0, cents(5_000_000)), ("3000", 0, cents(15_000_000)),
        ("3100", 0, cents(4_000_000)),
    ])

    suppliers = [(i, s[0], "Material Supplier", rng.choice([30, 45, 60]))
                 for i, s in enumerate(MATERIAL_SUPPLIERS, start=1)]
    service_ids: dict[str, list[int]] = defaultdict(list)
    for category, names in SERVICE_SUPPLIERS.items():
        for name in names:
            supplier_id = len(suppliers) + 1
            suppliers.append((supplier_id, name, category, rng.choice([30, 45])))
            service_ids[category].append(supplier_id)
    terms_of = {s[0]: s[3] for s in suppliers}

    def add_invoice(when: date, supplier_id: int, project_id: int, po_id: int | None,
                    grn_id: int | None, category: str, amount: int, received: int | None) -> None:
        """received is the goods-receipt value, or None for an invoice with no order."""
        invoice_id = len(invoices) + 1
        invoice_no = f"SINV-{invoice_id:05d}"
        due = when + timedelta(days=terms_of[supplier_id])
        retention = amount * 5 // 100 if category == "Subcontractor" else 0
        payable = amount - retention
        account = CATEGORIES[category][1]
        if received is None:
            match = "No PO"
            lines = [(account, amount, 0)]
        else:
            match = "Matched" if amount == received else "Price Variance"
            lines = [("2010", received, 0), (account, amount - received, 0)]
        lines += [("2000", 0, payable), ("2020", 0, retention)]
        ledger.post(when, "Supplier Invoice", invoice_no, f"{category} invoice", lines, project_id)

        paid = 0
        paid_on = due + timedelta(days=rng.randint(-3, 12))
        if paid_on <= AS_OF:
            paid = payable
            payments.append((len(payments) + 1, invoice_id, paid_on.isoformat(), rm(payable)))
            ledger.post(paid_on, "Supplier Payment", invoice_no, "Supplier payment",
                        [("2000", payable, 0), ("1000", 0, payable)], project_id)
        invoices.append((invoice_id, invoice_no, supplier_id, project_id, po_id, grn_id,
                         when.isoformat(), due.isoformat(), category, rm(amount), rm(retention),
                         rm(payable), rm(paid), rm(payable - paid), match,
                         status_for(payable, paid)))

    def procure(requested: date, project_id: int, category: str, supplier_id: int,
                lines: list[tuple[int, float, int]], total: int, delay: tuple[int, int]) -> None:
        """Run one requisition through order, receipt, invoice and payment."""
        if requested > AS_OF:
            return
        pr_id = len(requisitions) + 1
        approved = requested + timedelta(days=rng.randint(1, 6))
        outcome = rng.choices(["Approved", "Rejected", "Pending"], [96, 2, 2])[0]
        if outcome == "Pending" or approved > AS_OF:
            requisitions.append((pr_id, f"PR-{pr_id:05d}", project_id, requested.isoformat(),
                                 category, rm(total), None, "Pending"))
            return
        requisitions.append((pr_id, f"PR-{pr_id:05d}", project_id, requested.isoformat(), category,
                             rm(total), approved.isoformat() if outcome == "Approved" else None, outcome))
        if outcome == "Rejected":
            return
        ordered = approved + timedelta(days=rng.randint(0, 4))
        if ordered > AS_OF:
            return
        po_id = len(orders) + 1
        promised = ordered + timedelta(days=rng.randint(7, 16))
        for material_id, quantity, price in lines:
            order_lines.append((len(order_lines) + 1, po_id, material_id, quantity,
                                rm(price), rm(int(round(quantity * price)))))

        parts = [total]
        if category == "Materials" and rng.random() < 0.12:
            first = total * 6 // 10
            parts = [first, total - first]
        received_total = 0
        arrived = promised + timedelta(days=rng.randint(*delay))
        for value in parts:
            if arrived > AS_OF:
                break
            grn_id = len(receipts_in) + 1
            grn_no = f"GRN-{grn_id:05d}"
            receipts_in.append((grn_id, grn_no, po_id, arrived.isoformat(), rm(value),
                                max((arrived - promised).days, 0)))
            received_total += value
            ledger.post(arrived, "Goods Receipt", grn_no, f"{category} received",
                        [(CATEGORIES[category][1], value, 0), ("2010", 0, value)], project_id)
            billed_on = arrived + timedelta(days=rng.randint(1, 10))
            if billed_on <= AS_OF:
                billed = value
                if rng.random() < 0.035:
                    billed = int(value * rng.uniform(1.04, 1.12))
                add_invoice(billed_on, supplier_id, project_id, po_id, grn_id, category, billed, value)
            arrived += timedelta(days=rng.randint(6, 15))

        state = "Received" if received_total == total else ("Partially Received" if received_total else "Open")
        orders.append((po_id, f"PO-{po_id:05d}", pr_id, project_id, supplier_id, ordered.isoformat(),
                       promised.isoformat(), category, rm(total), rm(received_total), state))

    project_meta = []
    for project_id, (code, name, client_id, state, start, months, contract, overrun) in enumerate(PROJECTS, start=1):
        margin = rng.uniform(0.12, 0.16)
        budget = {c: cents(contract * (1 - margin) * share) for c, (share, _a) in CATEGORIES.items()}

        approved_vos = []
        for number in range(1, rng.randint(3, 5) + 1):
            when = add_months(start, rng.randint(3, months - 3)) + timedelta(days=rng.randint(0, 27))
            if when > AS_OF:
                continue
            amount = cents(contract * rng.uniform(0.004, 0.018))
            recent = (AS_OF - when).days < 60
            status = "Pending" if recent else rng.choices(["Approved", "Rejected"], [85, 15])[0]
            vo_id = len(variations) + 1
            variations.append((vo_id, f"VO-{vo_id:03d}", project_id, when.isoformat(),
                               rng.choice(["Additional piling", "Design change", "Extra M and E works",
                                           "Upgraded finishes", "Site condition works"]),
                               rm(amount), status))
            if status == "Approved":
                approved_vos.append((when, amount))

        claim_number, retention_total = 0, 0
        for index in range(months):
            month = add_months(start, index)
            if month > AS_OF:
                break
            step = s_curve((index + 1) / months) - s_curve(index / months)

            # Purchases
            for category in CATEGORIES:
                planned = int(budget[category] * step * overrun.get(category, 1.0) * rng.uniform(0.96, 1.04))
                if category == "Labour":
                    pay_day = month.replace(day=27)
                    ledger.post(pay_day, "Payroll", f"SITE-{code}-{month:%Y%m}", "Site labour payroll",
                                [("5200", planned, 0), ("1000", 0, planned)], project_id)
                    continue
                if category == "Materials":
                    for material_id, weight in zip(range(1, 11), MATERIAL_WEIGHTS):
                        value = planned * weight // sum(MATERIAL_WEIGHTS)
                        if value < cents(1_500):
                            continue
                        options = [i for i, s in enumerate(MATERIAL_SUPPLIERS, start=1) if material_id in s[1]]
                        supplier_id = rng.choice(options)
                        _n, _m, factor, delay = MATERIAL_SUPPLIERS[supplier_id - 1]
                        requested = month + timedelta(days=rng.randint(0, 9))
                        price = MATERIALS[material_id - 1][3] * factor * rng.uniform(0.98, 1.02)
                        if material_id == 2 and requested >= date(2026, 3, 1):
                            price *= 1.18
                        price_sen = cents(price)
                        quantity = float(max(round(value / price_sen), 1))
                        total = int(round(quantity * price_sen))
                        if rng.random() < (0.16 if code == "PRJ-03" else 0.015):
                            billed_on = requested + timedelta(days=rng.randint(5, 20))
                            if billed_on <= AS_OF:
                                add_invoice(billed_on, supplier_id, project_id, None, None,
                                            "Materials", total, None)
                            continue
                        procure(requested, project_id, "Materials", supplier_id,
                                [(material_id, quantity, price_sen)], total, delay)
                else:
                    supplier_id = rng.choice(service_ids[category])
                    procure(month + timedelta(days=rng.randint(0, 5)), project_id, category,
                            supplier_id, [], planned, (-2, 4))

            # Progress claim to the client
            claim_date = month.replace(day=28)
            if claim_date > AS_OF:
                continue
            value = int(cents(contract) * step)
            value += sum(a for d, a in approved_vos if (d.year, d.month) == (month.year, month.month))
            claim_number += 1
            claim_id = len(claims) + 1
            claim_no = f"{code}-C{claim_number:02d}"
            certified_on = claim_date + timedelta(days=rng.randint(12, 25))
            if certified_on > AS_OF:
                claims.append((claim_id, claim_no, project_id, claim_date.isoformat(), None, None,
                               rm(value), 0.0, 0.0, 0.0, 0.0, 0.0, "Awaiting Certification"))
                continue
            certified = int(value * rng.uniform(0.97, 1.0))
            retention = min(certified // 10, cents(contract) * 5 // 100 - retention_total)
            retention_total += retention
            net = certified - retention
            terms = CLIENTS[client_id - 1][3]
            due = certified_on + timedelta(days=terms)
            ledger.post(certified_on, "Progress Claim", claim_no, "Certified progress claim",
                        [("1100", net, 0), ("1110", retention, 0), ("4000", 0, certified)], project_id)
            delay = rng.randint(-5, 10)
            amount_paid = net
            if client_id == SLOW_CLIENT:
                delay = rng.randint(45, 120)
                if rng.random() < 0.2:
                    amount_paid = 0
            elif CLIENTS[client_id - 1][2] == "Government":
                delay = rng.randint(0, 25)
            paid = 0
            paid_on = due + timedelta(days=delay)
            if amount_paid and paid_on <= AS_OF:
                paid = amount_paid
                receipts.append((len(receipts) + 1, claim_id, paid_on.isoformat(), rm(paid)))
                ledger.post(paid_on, "Client Receipt", claim_no, "Client payment",
                            [("1000", paid, 0), ("1100", 0, paid)], project_id)
            claims.append((claim_id, claim_no, project_id, claim_date.isoformat(),
                           certified_on.isoformat(), due.isoformat(), rm(value), rm(certified),
                           rm(retention), rm(net), rm(paid), rm(net - paid), status_for(net, paid)))
        project_meta.append((project_id, code, name, client_id, state, start, months, contract, budget,
                             sum(a for _d, a in approved_vos)))

    # Head office costs, depreciation and loan
    overhead_budget = []
    account_names = {a[0]: a[1] for a in ACCOUNTS}
    department_names = dict(DEPARTMENTS)
    for index in range(24):
        month = add_months(START, index)
        costs = [("6000", d, base, month.replace(day=27)) for d, base in HEAD_OFFICE_SALARY.items()]
        costs += [(a, d, base, month.replace(day=15)) for a, d, base in HEAD_OFFICE_COSTS]
        for account, department, base, when in costs:
            actual = cents(base * rng.uniform(0.96, 1.04))
            if account == "6300" and month >= date(2026, 1, 1):
                actual = int(actual * 1.3)
            ledger.post(when, "Head Office", f"HO-{month:%Y%m}", account_names[account],
                        [(account, actual, 0), ("1000", 0, actual)], department=department)
            overhead_budget.append((month.strftime("%Y-%m"), department_names[department],
                                    account_names[account], float(base), rm(actual)))
        ledger.post(month.replace(day=28), "Depreciation", f"DEP-{month:%Y%m}", "Monthly depreciation",
                    [("6500", cents(75_000), 0), ("1510", 0, cents(75_000))], department=1)
        principal = cents(100_000)
        interest = (cents(5_000_000) - principal * index) * 55 // 1000 // 12  # 5.5% a year
        ledger.post(month.replace(day=25), "Loan", f"LOAN-{month:%Y%m}", "Loan instalment",
                    [("2500", principal, 0), ("6800", interest, 0), ("1000", 0, principal + interest)],
                    department=2)

    # Summaries, all derived from the ledger and documents above
    entry_period = {e[0]: e[2] for e in ledger.entries}
    category_of = {account: c for c, (_s, account) in CATEGORIES.items()}
    actual: dict[tuple[int, str], int] = defaultdict(int)
    monthly: dict[tuple[str, int], list[int]] = defaultdict(lambda: [0, 0])
    for _id, entry_id, account, project, _dept, debit, credit in ledger.lines:
        net = cents(debit) - cents(credit)
        if account in category_of:
            actual[(project, category_of[account])] += net
            monthly[(entry_period[entry_id], project)][1] += net
        elif account == "4000":
            monthly[(entry_period[entry_id], project)][0] -= net
    commitment: dict[tuple[int, str], int] = defaultdict(int)
    for order in orders:
        commitment[(order[3], order[7])] += cents(order[8]) - cents(order[9])

    projects, cost_summary = [], []
    for project_id, code, name, client_id, state, start, months, contract, budget, vo_total in project_meta:
        for category, planned in budget.items():
            spent = actual[(project_id, category)]
            open_value = commitment[(project_id, category)]
            cost_summary.append((code, name, category, rm(planned), rm(spent), rm(open_value),
                                 rm(planned - spent - open_value)))
        own = [c for c in claims if c[2] == project_id]
        certified = sum(cents(c[7]) for c in own)
        revised = cents(contract) + vo_total
        end = add_months(start, months) - timedelta(days=1)
        projects.append((project_id, code, name, client_id, state, start.isoformat(), end.isoformat(),
                         float(contract), rm(vo_total), rm(revised), rm(sum(budget.values())),
                         rm(sum(actual[(project_id, c)] for c in CATEGORIES)),
                         rm(sum(commitment[(project_id, c)] for c in CATEGORIES)),
                         rm(certified), rm(sum(cents(c[10]) for c in own)),
                         rm(sum(cents(c[8]) for c in own)), round(100 * certified / revised, 1),
                         "Completed" if end <= AS_OF else "Ongoing"))
    names = {p[0]: (p[1], p[2]) for p in projects}
    project_monthly = [(period, *names[project], rm(revenue), rm(cost), rm(revenue - cost))
                       for (period, project), (revenue, cost) in sorted(monthly.items())]

    # Project accounting: forecast, work in progress and cash position
    project_account = []
    for project in projects:
        project_id, code, name = project[0], project[1], project[2]
        start, months = PROJECTS[project_id - 1][4], PROJECTS[project_id - 1][5]
        revised, budget_total, cost = cents(project[9]), cents(project[10]), cents(project[11])
        open_value, certified = cents(project[12]), cents(project[13])
        status = project[17]
        elapsed = (AS_OF.year - start.year) * 12 + AS_OF.month - start.month + 1
        remaining = 0 if status == "Completed" else int(budget_total * (1 - s_curve(elapsed / months)))
        forecast = cost + max(remaining, open_value)
        complete = cost / forecast
        earned = int(revised * complete)
        retention_payable = sum(cents(i[10]) for i in invoices if i[3] == project_id)
        cash_in = sum(cents(l[5]) for l in ledger.lines if l[2] == "1000" and l[3] == project_id)
        cash_out = sum(cents(l[6]) for l in ledger.lines if l[2] == "1000" and l[3] == project_id)
        project_account.append((
            code, name, status, rm(revised), rm(cost), rm(forecast), rm(revised - forecast),
            round(100 * (revised - forecast) / revised, 1), round(100 * complete, 1), rm(earned),
            rm(certified), rm(max(earned - certified, 0)), rm(max(certified - earned, 0)),
            project[15], rm(retention_payable), rm(cash_in), rm(cash_out), rm(cash_in - cash_out)))

    flows: dict[tuple[int, str], list[int]] = defaultdict(lambda: [0, 0])
    for _id, entry_id, account, project, _dept, debit, credit in ledger.lines:
        if account == "1000" and project is not None:
            flows[(project, entry_period[entry_id])][0] += cents(debit)
            flows[(project, entry_period[entry_id])][1] += cents(credit)
    cash_flow, running = [], defaultdict(int)
    for (project, period), (money_in, money_out) in sorted(flows.items()):
        running[project] += money_in - money_out
        cash_flow.append((period, *names[project], rm(money_in), rm(money_out),
                          rm(money_in - money_out), rm(running[project])))

    tables = {
        "project_account": project_account, "project_cash_flow": cash_flow,
        "accounts": ACCOUNTS, "departments": DEPARTMENTS, "clients": CLIENTS, "projects": projects,
        "variation_orders": variations, "project_cost_summary": cost_summary,
        "project_monthly": project_monthly, "progress_claims": claims, "client_receipts": receipts,
        "suppliers": suppliers, "materials": MATERIALS, "purchase_requisitions": requisitions,
        "purchase_orders": orders, "purchase_order_lines": order_lines, "goods_receipts": receipts_in,
        "supplier_invoices": invoices, "supplier_payments": payments,
        "overhead_budget_vs_actual": overhead_budget, "journal_entries": ledger.entries,
        "journal_lines": ledger.lines,
    }
    DB_PATH.unlink(missing_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    for table, rows in tables.items():
        marks = ",".join("?" * len(rows[0]))
        conn.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)
        print(f"{table:28} {len(rows):>7}")
    conn.commit()
    conn.close()
    print(f"Wrote {DB_PATH}")


if __name__ == "__main__":
    main()
