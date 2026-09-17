"""CSV rows for ``GET /api/v1/analytics/export/`` built from serialized report data."""

import csv
import io

INJECTION_PREFIXES = ("=", "+", "-", "@")

MESSAGE_COLUMNS = ("date", "sent", "delivered", "read", "failed", "received")
TEMPLATE_COLUMNS = (
    "template_id",
    "name",
    "language",
    "category",
    "sent",
    "delivered",
    "read",
    "failed",
    "delivery_rate",
    "read_rate",
)
CAMPAIGN_COLUMNS = (
    "id",
    "name",
    "status",
    "started_at",
    "total_count",
    "sent_count",
    "delivered_count",
    "read_count",
    "failed_count",
    "replied_count",
    "delivery_rate",
    "read_rate",
    "reply_rate",
)
TEAM_COLUMNS = (
    "user_id",
    "name",
    "email",
    "role",
    "messages_sent",
    "conversations_assigned",
    "conversations_closed",
)
COMMERCE_COLUMNS = ("date", "orders", "revenue_inr")


def paise_to_inr(paise: int) -> str:
    rupees, remainder = divmod(int(paise), 100)
    return f"{rupees}.{remainder:02d}"


def escape_cell(value) -> str:
    """Stringify a cell; text a spreadsheet would run as a formula gets a leading quote."""
    text = "" if value is None else str(value)
    if text.startswith(INJECTION_PREFIXES):
        return "'" + text
    return text


def report_table(report: str, data: dict) -> tuple[tuple[str, ...], list[dict]]:
    if report == "messages":
        return MESSAGE_COLUMNS, data["series"]
    if report == "commerce":
        rows = [
            {
                "date": point["date"],
                "orders": point["orders"],
                "revenue_inr": paise_to_inr(point["revenue_paise"]),
            }
            for point in data["series"]
        ]
        return COMMERCE_COLUMNS, rows
    columns = {"templates": TEMPLATE_COLUMNS, "campaigns": CAMPAIGN_COLUMNS, "team": TEAM_COLUMNS}
    return columns[report], data["results"]


def render_csv(report: str, data: dict) -> str:
    columns, rows = report_table(report, data)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([escape_cell(row.get(column)) for column in columns])
    return buffer.getvalue()


def filename(report: str, data: dict) -> str:
    return f"upchatz-{report}-{data['range']['from']}-{data['range']['to']}.csv"
