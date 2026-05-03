"""
Advanced Expense Tracker MCP Server
Author: Senior AI Engineer Build
Version: 2.0.0
"""

from __future__ import annotations

import os
import json
import sqlite3
import csv
import io
from datetime import datetime, date
from typing import Optional, List
from contextlib import contextmanager

from fastmcp import FastMCP
from pydantic import BaseModel, Field, field_validator

# ─────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.environ.get("EXPENSE_DB_PATH", os.path.join(BASE_DIR, "expenses.db"))
CATEGORIES_PATH = os.path.join(BASE_DIR, "categories.json")
DEFAULT_CURRENCY = os.environ.get("DEFAULT_CURRENCY", "INR")

mcp = FastMCP(
    "AdvancedExpenseTracker",
    instructions=(
        "A production-grade expense tracking MCP server. "
        "Supports multi-currency, budgets, recurring expenses, "
        "analytics, CSV export, and full CRUD on expenses."
    ),
)


# ─────────────────────────────────────────────
#  Pydantic Models
# ─────────────────────────────────────────────
class Expense(BaseModel):
    date: str = Field(..., description="ISO date string YYYY-MM-DD")
    amount: float = Field(..., gt=0, description="Positive expense amount")
    category: str = Field(..., min_length=1)
    subcategory: str = Field(default="")
    note: str = Field(default="")
    currency: str = Field(default=DEFAULT_CURRENCY)
    tags: str = Field(default="", description="Comma-separated tags")
    is_recurring: bool = Field(default=False)
    recurrence_interval: Optional[str] = Field(
        default=None, description="daily | weekly | monthly | yearly"
    )

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("date must be YYYY-MM-DD format")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        return v.upper()


class Budget(BaseModel):
    category: str
    monthly_limit: float = Field(..., gt=0)
    currency: str = Field(default=DEFAULT_CURRENCY)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        return v.upper()


# ─────────────────────────────────────────────
#  Database
# ─────────────────────────────────────────────
@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                date             TEXT    NOT NULL,
                amount           REAL    NOT NULL CHECK(amount > 0),
                category         TEXT    NOT NULL,
                subcategory      TEXT    DEFAULT '',
                note             TEXT    DEFAULT '',
                currency         TEXT    DEFAULT 'INR',
                tags             TEXT    DEFAULT '',
                is_recurring     INTEGER DEFAULT 0,
                recurrence_interval TEXT DEFAULT NULL,
                created_at       TEXT    DEFAULT (datetime('now')),
                updated_at       TEXT    DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_expenses_date     ON expenses(date);
            CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);

            CREATE TABLE IF NOT EXISTS budgets (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                category      TEXT    NOT NULL UNIQUE,
                monthly_limit REAL    NOT NULL CHECK(monthly_limit > 0),
                currency      TEXT    DEFAULT 'INR',
                created_at    TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                action     TEXT NOT NULL,
                table_name TEXT NOT NULL,
                record_id  INTEGER,
                payload    TEXT,
                ts         TEXT DEFAULT (datetime('now'))
            );
            """
        )


init_db()


# ─────────────────────────────────────────────
#  Helper utilities
# ─────────────────────────────────────────────
def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _log_audit(conn: sqlite3.Connection, action: str, table: str, record_id: int, payload: dict) -> None:
    conn.execute(
        "INSERT INTO audit_log(action, table_name, record_id, payload) VALUES (?,?,?,?)",
        (action, table, record_id, json.dumps(payload)),
    )


# ─────────────────────────────────────────────
#  MCP TOOLS — CRUD
# ─────────────────────────────────────────────
@mcp.tool()
def add_expense(
    date: str,
    amount: float,
    category: str,
    subcategory: str = "",
    note: str = "",
    currency: str = DEFAULT_CURRENCY,
    tags: str = "",
    is_recurring: bool = False,
    recurrence_interval: Optional[str] = None,
) -> dict:
    """Add a validated expense. Returns the new record with id and budget warning if applicable."""
    exp = Expense(
        date=date,
        amount=amount,
        category=category,
        subcategory=subcategory,
        note=note,
        currency=currency,
        tags=tags,
        is_recurring=is_recurring,
        recurrence_interval=recurrence_interval,
    )
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO expenses
               (date, amount, category, subcategory, note, currency, tags, is_recurring, recurrence_interval)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                exp.date, exp.amount, exp.category, exp.subcategory,
                exp.note, exp.currency, exp.tags,
                int(exp.is_recurring), exp.recurrence_interval,
            ),
        )
        new_id = cur.lastrowid
        _log_audit(conn, "INSERT", "expenses", new_id, exp.model_dump())

        # Budget check
        month_prefix = exp.date[:7]
        row = conn.execute(
            "SELECT SUM(amount) FROM expenses WHERE category=? AND date LIKE ?",
            (exp.category, f"{month_prefix}%"),
        ).fetchone()
        month_total = row[0] or 0.0

        budget_row = conn.execute(
            "SELECT monthly_limit FROM budgets WHERE category=?", (exp.category,)
        ).fetchone()

    result: dict = {"status": "ok", "id": new_id, "month_total_for_category": round(month_total, 2)}
    if budget_row:
        limit = budget_row[0]
        pct = round(month_total / limit * 100, 1)
        result["budget_status"] = {
            "limit": limit,
            "used_pct": pct,
            "warning": pct >= 80,
        }
    return result


@mcp.tool()
def update_expense(
    expense_id: int,
    date: Optional[str] = None,
    amount: Optional[float] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    note: Optional[str] = None,
    currency: Optional[str] = None,
    tags: Optional[str] = None,
) -> dict:
    """Partially update an existing expense by id."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM expenses WHERE id=?", (expense_id,)).fetchone()
        if not row:
            return {"status": "error", "message": f"Expense {expense_id} not found"}

        current = dict(row)
        updates = {
            "date": date or current["date"],
            "amount": amount if amount is not None else current["amount"],
            "category": category or current["category"],
            "subcategory": subcategory if subcategory is not None else current["subcategory"],
            "note": note if note is not None else current["note"],
            "currency": (currency or current["currency"]).upper(),
            "tags": tags if tags is not None else current["tags"],
            "updated_at": datetime.utcnow().isoformat(),
        }
        conn.execute(
            """UPDATE expenses SET date=?, amount=?, category=?, subcategory=?,
               note=?, currency=?, tags=?, updated_at=? WHERE id=?""",
            (*updates.values(), expense_id),
        )
        _log_audit(conn, "UPDATE", "expenses", expense_id, updates)
    return {"status": "ok", "id": expense_id, "updated_fields": updates}


@mcp.tool()
def delete_expense(expense_id: int) -> dict:
    """Permanently delete an expense by id. Logs to audit trail."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM expenses WHERE id=?", (expense_id,)).fetchone()
        if not row:
            return {"status": "error", "message": f"Expense {expense_id} not found"}
        _log_audit(conn, "DELETE", "expenses", expense_id, dict(row))
        conn.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
    return {"status": "ok", "deleted_id": expense_id}


@mcp.tool()
def list_expenses(
    start_date: str,
    end_date: str,
    category: Optional[str] = None,
    currency: Optional[str] = None,
    tags: Optional[str] = None,
    is_recurring: Optional[bool] = None,
    limit: int = 200,
    offset: int = 0,
) -> dict:
    """List expenses with rich filters. Returns paginated results + total count."""
    query = "SELECT * FROM expenses WHERE date BETWEEN ? AND ?"
    params: list = [start_date, end_date]

    if category:
        query += " AND category = ?"
        params.append(category)
    if currency:
        query += " AND currency = ?"
        params.append(currency.upper())
    if tags:
        for tag in tags.split(","):
            query += " AND tags LIKE ?"
            params.append(f"%{tag.strip()}%")
    if is_recurring is not None:
        query += " AND is_recurring = ?"
        params.append(int(is_recurring))

    count_query = query.replace("SELECT *", "SELECT COUNT(*)")

    with get_conn() as conn:
        total = conn.execute(count_query, params).fetchone()[0]
        rows = conn.execute(
            query + " ORDER BY date DESC, id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "expenses": [_row_to_dict(r) for r in rows],
    }


# ─────────────────────────────────────────────
#  MCP TOOLS — ANALYTICS
# ─────────────────────────────────────────────
@mcp.tool()
def summarize(
    start_date: str,
    end_date: str,
    category: Optional[str] = None,
    group_by: str = "category",
) -> dict:
    """
    Summarize expenses. group_by: 'category' | 'month' | 'day' | 'currency'.
    Returns totals, counts, averages, and grand total.
    """
    valid_groups = {"category", "month", "day", "currency"}
    if group_by not in valid_groups:
        return {"status": "error", "message": f"group_by must be one of {valid_groups}"}

    group_expr = {
        "category": "category",
        "month": "strftime('%Y-%m', date)",
        "day": "date",
        "currency": "currency",
    }[group_by]

    query = f"""
        SELECT {group_expr} AS group_key,
               COUNT(*)          AS count,
               SUM(amount)       AS total,
               AVG(amount)       AS average,
               MIN(amount)       AS min_amount,
               MAX(amount)       AS max_amount
        FROM expenses
        WHERE date BETWEEN ? AND ?
    """
    params: list = [start_date, end_date]
    if category:
        query += " AND category = ?"
        params.append(category)
    query += " GROUP BY group_key ORDER BY total DESC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        grand = conn.execute(
            "SELECT SUM(amount), COUNT(*) FROM expenses WHERE date BETWEEN ? AND ?",
            [start_date, end_date],
        ).fetchone()

    summary = [
        {
            "group": r["group_key"],
            "count": r["count"],
            "total": round(r["total"], 2),
            "average": round(r["average"], 2),
            "min": round(r["min_amount"], 2),
            "max": round(r["max_amount"], 2),
        }
        for r in rows
    ]
    return {
        "group_by": group_by,
        "period": {"start": start_date, "end": end_date},
        "grand_total": round(grand[0] or 0, 2),
        "grand_count": grand[1] or 0,
        "breakdown": summary,
    }


@mcp.tool()
def top_expenses(
    start_date: str,
    end_date: str,
    n: int = 10,
    category: Optional[str] = None,
) -> List[dict]:
    """Return the top-N most expensive transactions in a date range."""
    query = "SELECT * FROM expenses WHERE date BETWEEN ? AND ?"
    params: list = [start_date, end_date]
    if category:
        query += " AND category = ?"
        params.append(category)
    query += f" ORDER BY amount DESC LIMIT {max(1, min(n, 100))}"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_dict(r) for r in rows]


@mcp.tool()
def monthly_trend(year: int, category: Optional[str] = None) -> dict:
    """Return month-by-month expense totals for a given year."""
    query = """
        SELECT strftime('%m', date) AS month,
               SUM(amount) AS total,
               COUNT(*)    AS count
        FROM expenses
        WHERE date LIKE ?
    """
    params: list = [f"{year}-%"]
    if category:
        query += " AND category = ?"
        params.append(category)
    query += " GROUP BY month ORDER BY month ASC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    month_names = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    data = {r["month"]: {"total": round(r["total"], 2), "count": r["count"]} for r in rows}
    trend = [
        {
            "month": month_names[int(m) - 1],
            "month_num": m,
            "total": data.get(f"{int(m):02d}", {}).get("total", 0.0),
            "count": data.get(f"{int(m):02d}", {}).get("count", 0),
        }
        for m in [f"{i:02d}" for i in range(1, 13)]
    ]
    return {"year": year, "category": category, "trend": trend}


# ─────────────────────────────────────────────
#  MCP TOOLS — BUDGET
# ─────────────────────────────────────────────
@mcp.tool()
def set_budget(category: str, monthly_limit: float, currency: str = DEFAULT_CURRENCY) -> dict:
    """Set or update a monthly budget limit for a category."""
    b = Budget(category=category, monthly_limit=monthly_limit, currency=currency)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO budgets(category, monthly_limit, currency)
               VALUES (?,?,?)
               ON CONFLICT(category) DO UPDATE SET monthly_limit=excluded.monthly_limit,
               currency=excluded.currency""",
            (b.category, b.monthly_limit, b.currency),
        )
    return {"status": "ok", "category": b.category, "monthly_limit": b.monthly_limit, "currency": b.currency}


@mcp.tool()
def get_budget_status(month: Optional[str] = None) -> List[dict]:
    """
    Get current month's budget usage for all categories.
    month: YYYY-MM (defaults to current month).
    """
    if not month:
        month = datetime.now().strftime("%Y-%m")

    with get_conn() as conn:
        budgets = conn.execute("SELECT * FROM budgets").fetchall()
        results = []
        for b in budgets:
            row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE category=? AND date LIKE ?",
                (b["category"], f"{month}%"),
            ).fetchone()
            spent = round(row[0], 2)
            limit = b["monthly_limit"]
            remaining = round(limit - spent, 2)
            pct = round(spent / limit * 100, 1) if limit > 0 else 0
            results.append(
                {
                    "category": b["category"],
                    "monthly_limit": limit,
                    "spent": spent,
                    "remaining": remaining,
                    "used_pct": pct,
                    "status": "over_budget" if spent > limit else ("warning" if pct >= 80 else "ok"),
                    "currency": b["currency"],
                }
            )
    results.sort(key=lambda x: x["used_pct"], reverse=True)
    return results


@mcp.tool()
def delete_budget(category: str) -> dict:
    """Remove a budget limit for a category."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM budgets WHERE category=?", (category,))
        if cur.rowcount == 0:
            return {"status": "error", "message": f"No budget found for '{category}'"}
    return {"status": "ok", "deleted_category": category}


# ─────────────────────────────────────────────
#  MCP TOOLS — EXPORT
# ─────────────────────────────────────────────
@mcp.tool()
def export_csv(start_date: str, end_date: str, category: Optional[str] = None) -> str:
    """Export expenses as a CSV string for the given date range."""
    query = "SELECT id,date,amount,category,subcategory,note,currency,tags,is_recurring FROM expenses WHERE date BETWEEN ? AND ?"
    params: list = [start_date, end_date]
    if category:
        query += " AND category=?"
        params.append(category)
    query += " ORDER BY date ASC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "date", "amount", "category", "subcategory", "note", "currency", "tags", "is_recurring"])
    for r in rows:
        writer.writerow(list(r))
    return output.getvalue()


@mcp.tool()
def export_json(start_date: str, end_date: str, category: Optional[str] = None) -> str:
    """Export expenses as a JSON string for the given date range."""
    result = list_expenses(start_date=start_date, end_date=end_date, category=category, limit=10000)
    return json.dumps(result, indent=2, default=str)


# ─────────────────────────────────────────────
#  MCP RESOURCES
# ─────────────────────────────────────────────
@mcp.resource("expense://categories", mime_type="application/json")
def categories() -> str:
    """Available expense categories loaded from categories.json."""
    try:
        with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return json.dumps({"error": "categories.json not found"})


@mcp.resource("expense://schema", mime_type="application/json")
def schema() -> str:
    """Returns the JSON Schema for the Expense model."""
    return Expense.model_json_schema().__str__()


@mcp.resource("expense://health", mime_type="application/json")
def health() -> str:
    """Health check: returns DB stats."""
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        budgets = conn.execute("SELECT COUNT(*) FROM budgets").fetchone()[0]
        oldest = conn.execute("SELECT MIN(date) FROM expenses").fetchone()[0]
        latest = conn.execute("SELECT MAX(date) FROM expenses").fetchone()[0]
    return json.dumps({
        "status": "healthy",
        "db_path": DB_PATH,
        "total_expenses": total,
        "active_budgets": budgets,
        "date_range": {"oldest": oldest, "latest": latest},
        "server_time": datetime.utcnow().isoformat(),
    })


# ─────────────────────────────────────────────
#  Entrypoint
# ─────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run()
