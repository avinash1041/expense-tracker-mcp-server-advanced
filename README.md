# 💰 Advanced Expense Tracker MCP Server

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)
[![FastMCP](https://img.shields.io/badge/FastMCP-0.9%2B-green)](https://github.com/jlowin/fastmcp)
[![Pydantic](https://img.shields.io/badge/Pydantic-v2-red)](https://docs.pydantic.dev)

A **production-grade** Model Context Protocol (MCP) server for expense tracking — built for senior AI engineers who care about type safety, clean architecture, observability, and real-world robustness.

This is a ground-up rewrite of the [basic expense-tracker-mcp-server](https://github.com/campusx-official/expense-tracker-mcp-server), with 10× more tools, proper validation, budget management, analytics, audit logging, and CSV/JSON export.

---

## ✨ Features at a Glance

| Feature | Basic | **This Repo** |
|---|:---:|:---:|
| Add / List / Summarize | ✅ | ✅ |
| Update & Delete (soft audit) | ❌ | ✅ |
| Pydantic v2 validation | ❌ | ✅ |
| Multi-currency support | ❌ | ✅ |
| Tags & filtering | ❌ | ✅ |
| Recurring expenses | ❌ | ✅ |
| Budget management | ❌ | ✅ |
| Budget alerts (80% / over) | ❌ | ✅ |
| Monthly trend analytics | ❌ | ✅ |
| Top-N expenses | ❌ | ✅ |
| CSV & JSON export | ❌ | ✅ |
| Audit log table | ❌ | ✅ |
| WAL mode SQLite | ❌ | ✅ |
| Health check resource | ❌ | ✅ |
| ENV-based config | ❌ | ✅ |
| Paginated list results | ❌ | ✅ |

---

## 🏗️ Architecture

```
expense-tracker-mcp-advanced/
├── main.py              # MCP server — all tools, resources, DB init
├── categories.json      # Editable category/subcategory taxonomy
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

**Stack:**
- **Transport**: stdio (default FastMCP) — works with Claude Desktop, Claude Code, any MCP client
- **ORM**: Raw SQLite3 with WAL journaling + context-manager connection pooling
- **Validation**: Pydantic v2 models with field-level validators
- **Schema**: 3 tables — `expenses`, `budgets`, `audit_log`

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/expense-tracker-mcp-advanced.git
cd expense-tracker-mcp-advanced

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure (Optional)

```bash
cp .env.example .env
# Edit .env to set EXPENSE_DB_PATH and DEFAULT_CURRENCY
```

### 3. Run the server

```bash
python main.py
```

---

## 🔌 Claude Desktop Integration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "expense-tracker": {
      "command": "python",
      "args": ["/absolute/path/to/main.py"],
      "env": {
        "DEFAULT_CURRENCY": "INR",
        "EXPENSE_DB_PATH": "/absolute/path/to/expenses.db"
      }
    }
  }
}
```

---

## 🛠️ MCP Tools Reference

### CRUD Tools

#### `add_expense`
```
date, amount, category
[subcategory, note, currency, tags, is_recurring, recurrence_interval]
```
Adds a validated expense. Returns the new `id`, this month's category total, and a budget warning if you've crossed 80% of your budget.

#### `update_expense`
```
expense_id, [date, amount, category, subcategory, note, currency, tags]
```
Partial update — only pass what you want to change. Full audit entry created.

#### `delete_expense`
```
expense_id
```
Hard delete with audit log entry before removal.

#### `list_expenses`
```
start_date, end_date
[category, currency, tags, is_recurring, limit=200, offset=0]
```
Paginated list with multi-filter support. Returns `total`, `limit`, `offset`, and `expenses[]`.

---

### Analytics Tools

#### `summarize`
```
start_date, end_date, [category, group_by="category|month|day|currency"]
```
Returns breakdown with `count`, `total`, `average`, `min`, `max` per group + grand total.

#### `top_expenses`
```
start_date, end_date, [n=10, category]
```
Returns the N most expensive transactions.

#### `monthly_trend`
```
year, [category]
```
Returns 12-month spend trend (all months, zero-filled) for the given year.

---

### Budget Tools

#### `set_budget`
```
category, monthly_limit, [currency]
```
Upserts a monthly budget cap for a category.

#### `get_budget_status`
```
[month="YYYY-MM"]
```
Returns all categories with `spent`, `remaining`, `used_pct`, and status (`ok` / `warning` / `over_budget`).

#### `delete_budget`
```
category
```
Removes a budget for the given category.

---

### Export Tools

#### `export_csv`
```
start_date, end_date, [category]
```
Returns a CSV string — pipe to a file or let Claude attach it.

#### `export_json`
```
start_date, end_date, [category]
```
Returns a pretty-printed JSON string of all matching expenses.

---

## 📡 MCP Resources

| URI | Description |
|-----|-------------|
| `expense://categories` | Full category/subcategory taxonomy (live from file) |
| `expense://schema` | Pydantic JSON Schema of the Expense model |
| `expense://health` | DB stats + server health check |

---

## 🗃️ Database Schema

```sql
expenses (
    id, date, amount, category, subcategory,
    note, currency, tags,
    is_recurring, recurrence_interval,
    created_at, updated_at
)

budgets (
    id, category UNIQUE, monthly_limit, currency, created_at
)

audit_log (
    id, action, table_name, record_id, payload (JSON), ts
)
```

---

## 💡 Example Prompts (with Claude)

```
"Add ₹450 food expense for today, category Groceries, tag 'weekly-shop'"

"Summarize my spending for May 2025 grouped by month"

"What are my top 5 expenses this month?"

"Set a ₹10,000 monthly budget for Food & Dining"

"Am I over budget anywhere this month?"

"Export all transport expenses for Q1 2025 as CSV"

"Show me the monthly trend for 2025"
```

---

## 🔐 Design Decisions

- **WAL mode**: SQLite WAL journaling is enabled for better concurrent read performance.
- **Pydantic v2**: All inputs validated before any DB write. No silent type coercion.
- **Audit log**: Every INSERT / UPDATE / DELETE writes to `audit_log` with full payload snapshot.
- **Budget alerts**: `add_expense` automatically computes month-to-date spend and warns at 80% / over-budget in the same response.
- **Env config**: DB path and default currency are environment-driven — no hardcoded paths.
- **Pagination**: `list_expenses` is paginated by default (limit=200) to prevent LLM context overload.

---

## 📦 Extending

1. **Add a new tool** — decorate a function with `@mcp.tool()`
2. **Add a new resource** — decorate with `@mcp.resource("expense://your-route")`
3. **Add a new table** — append to the `executescript` in `init_db()`

---

## 🤝 Contributing

PRs welcome. Please:
- Use type hints on all functions
- Add a docstring (used as the MCP tool description)
- Validate inputs via Pydantic before DB writes
- Log mutations to `audit_log`


---

> Built with [FastMCP](https://github.com/jlowin/fastmcp) · Inspired by [campusx-official/expense-tracker-mcp-server](https://github.com/campusx-official/expense-tracker-mcp-server)
