"""Report queries. Read-only aggregates, each filtered on the workspace first.

Every function returns plain data shaped like the matching response serializer (see
docs/contracts/analytics.md); rates are ``Decimal`` or ``None``.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, F, Max, Q, Sum
from django.db.models.functions import Coalesce, TruncDate

from apps.automations.models import AutomationRun
from apps.campaigns.models import Campaign
from apps.contacts.models import Contact
from apps.inbox.models import Conversation, Message
from apps.message_templates.models import MessageTemplate
from apps.orders.models import Order, OrderItem
from apps.tenants.models import Membership

from .ranges import ReportRange

RATE_PLACES = Decimal("0.0001")
TOP_FAILURE_REASONS = 10
MAX_TEMPLATE_ROWS = 50
MAX_CAMPAIGN_ROWS = 50
TOP_PRODUCTS = 10

OUTBOUND = Message.Direction.OUTBOUND
INBOUND = Message.Direction.INBOUND
SENT_STATUSES = (Message.Status.SENT, Message.Status.DELIVERED, Message.Status.READ)
DELIVERED_STATUSES = (Message.Status.DELIVERED, Message.Status.READ)
PAID_STATUSES = (Order.PaymentStatus.PAID, Order.PaymentStatus.COD_COLLECTED)


def rate(numerator: int, denominator: int) -> Decimal | None:
    if not denominator:
        return None
    return (Decimal(numerator) / Decimal(denominator)).quantize(RATE_PLACES, ROUND_HALF_UP)


def _in(field: str, start, end) -> Q:
    return Q(**{f"{field}__gte": start, f"{field}__lt": end})


def status_counts(extra: Q | None = None, *, received: bool = False) -> dict:
    """``Count`` annotations for the contract's message status definitions."""
    base = extra or Q()
    outbound = base & Q(direction=OUTBOUND)
    counts = {
        "sent": Count("pk", filter=outbound & Q(status__in=SENT_STATUSES)),
        "delivered": Count("pk", filter=outbound & Q(status__in=DELIVERED_STATUSES)),
        "read": Count("pk", filter=outbound & Q(status=Message.Status.READ)),
        "failed": Count("pk", filter=outbound & Q(status=Message.Status.FAILED)),
    }
    if received:
        counts["received"] = Count("pk", filter=base & Q(direction=INBOUND))
    return counts


def with_rates(row: dict) -> dict:
    row["delivery_rate"] = rate(row["delivered"], row["sent"])
    row["read_rate"] = rate(row["read"], row["delivered"])
    return row


def messages_in(workspace, start, end):
    return Message.objects.filter(workspace=workspace, created_at__gte=start, created_at__lt=end)


def orders_in(workspace, start, end):
    return Order.objects.filter(
        workspace=workspace, created_at__gte=start, created_at__lt=end
    ).exclude(status=Order.Status.DRAFT)


# --- overview ----------------------------------------------------------------------------------


def overview(workspace, rng: ReportRange, *, commerce: bool) -> dict:
    periods = {
        "current": (rng.start, rng.end),
        "previous": (rng.previous_start, rng.start),
    }
    totals: dict[str, dict] = {name: {} for name in periods}

    def aggregate(queryset, metrics: dict) -> None:
        """One query per model: ``metrics`` maps output key -> (Count/Sum factory by period)."""
        annotations = {
            f"{period}_{key}": factory(*bounds)
            for period, bounds in periods.items()
            for key, factory in metrics.items()
        }
        for name, value in queryset.aggregate(**annotations).items():
            period, key = name.split("_", 1)
            totals[period][key] = value or 0

    def message_metric(key: str):
        return lambda start, end: status_counts(_in("created_at", start, end), received=True)[key]

    aggregate(
        messages_in(workspace, rng.previous_start, rng.end),
        {
            f"messages_{key}": message_metric(key)
            for key in ("sent", "delivered", "read", "failed", "received")
        },
    )
    aggregate(
        Conversation.objects.filter(
            workspace=workspace, created_at__gte=rng.previous_start, created_at__lt=rng.end
        ),
        {"conversations_started": lambda s, e: Count("pk", filter=_in("created_at", s, e))},
    )
    aggregate(
        Contact.objects.filter(workspace=workspace).filter(
            _in("created_at", rng.previous_start, rng.end)
            | _in("opted_in_at", rng.previous_start, rng.end)
            | _in("opted_out_at", rng.previous_start, rng.end)
        ),
        {
            "contacts_added": lambda s, e: Count("pk", filter=_in("created_at", s, e)),
            "contacts_opted_in": lambda s, e: Count("pk", filter=_in("opted_in_at", s, e)),
            "contacts_opted_out": lambda s, e: Count("pk", filter=_in("opted_out_at", s, e)),
        },
    )
    aggregate(
        Campaign.objects.filter(
            workspace=workspace, started_at__gte=rng.previous_start, started_at__lt=rng.end
        ),
        {"campaigns_sent": lambda s, e: Count("pk", filter=_in("started_at", s, e))},
    )
    aggregate(
        AutomationRun.objects.filter(
            workspace=workspace,
            created_at__gte=rng.previous_start,
            created_at__lt=rng.end,
            status=AutomationRun.Status.SUCCEEDED,
        ),
        {"automation_runs": lambda s, e: Count("pk", filter=_in("created_at", s, e))},
    )
    if commerce:
        aggregate(
            orders_in(workspace, rng.previous_start, rng.end),
            {
                "orders": lambda s, e: Count("pk", filter=_in("created_at", s, e)),
                "revenue_paise": lambda s, e: Sum(
                    "total_paise",
                    filter=_in("created_at", s, e) & Q(payment_status__in=PAID_STATUSES),
                ),
            },
        )

    result = {"range": rng.as_dict()}
    for period, values in totals.items():
        values["delivery_rate"] = rate(values["messages_delivered"], values["messages_sent"])
        values["read_rate"] = rate(values["messages_read"], values["messages_delivered"])
        if not commerce:
            values["orders"] = None
            values["revenue_paise"] = None
        result[period] = values
    return result


# --- messages ----------------------------------------------------------------------------------


def daily_message_series(workspace, rng: ReportRange) -> list[dict]:
    rows = (
        messages_in(workspace, rng.start, rng.end)
        .annotate(day=TruncDate("created_at", tzinfo=rng.zone))
        .values("day")
        .annotate(**status_counts(received=True))
        .order_by("day")
    )
    by_day = {row.pop("day"): row for row in rows}
    empty = {"sent": 0, "delivered": 0, "read": 0, "failed": 0, "received": 0}
    return [{"date": day, **by_day.get(day, empty)} for day in rng.dates()]


def messages(workspace, rng: ReportRange) -> dict:
    outbound = messages_in(workspace, rng.start, rng.end).filter(direction=OUTBOUND)
    by_source = (
        outbound.exclude(source=Message.Source.INBOUND)
        .values("source")
        .annotate(**status_counts())
        .order_by("-sent", "source")
    )
    by_category = (
        outbound.values(category=F("template_category"))
        .annotate(**status_counts())
        .order_by("-sent", "category")
    )
    failure_reasons = (
        outbound.filter(status=Message.Status.FAILED)
        .values("error_code")
        .annotate(count=Count("pk"))
        .order_by("-count", "error_code")[:TOP_FAILURE_REASONS]
    )
    return {
        "range": rng.as_dict(),
        "series": daily_message_series(workspace, rng),
        "by_source": [with_rates(dict(row)) for row in by_source],
        "by_category": [dict(row) for row in by_category],
        "failure_reasons": [dict(row) for row in failure_reasons],
    }


# --- templates ---------------------------------------------------------------------------------


def templates(workspace, rng: ReportRange) -> dict:
    rows = [
        dict(row)
        for row in messages_in(workspace, rng.start, rng.end)
        .filter(direction=OUTBOUND, type=Message.Type.TEMPLATE)
        .values(name=F("template_name"), language=F("template_language"))
        .annotate(category=Max("template_category"))
        .annotate(**status_counts())
        .order_by("-sent", "name", "language")[:MAX_TEMPLATE_ROWS]
    ]
    template_ids: dict[tuple[str, str], object] = {}
    if rows:
        existing = (
            MessageTemplate.objects.filter(
                workspace=workspace,
                name__in={row["name"] for row in rows},
                language__in={row["language"] for row in rows},
            )
            .order_by("created_at")
            .values_list("name", "language", "pk")
        )
        for name, language, pk in existing:
            template_ids.setdefault((name, language), pk)
    results = [
        with_rates({"template_id": template_ids.get((row["name"], row["language"])), **row})
        for row in rows
    ]
    return {"range": rng.as_dict(), "results": results}


# --- campaigns ---------------------------------------------------------------------------------

CAMPAIGN_FIELDS = (
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
)


def campaigns(workspace, rng: ReportRange) -> dict:
    rows = (
        Campaign.objects.filter(workspace=workspace, started_at__gte=rng.start)
        .filter(started_at__lt=rng.end)
        .values(*CAMPAIGN_FIELDS)
        .order_by("-started_at", "-created_at")[:MAX_CAMPAIGN_ROWS]
    )
    results = []
    for row in rows:
        row = dict(row)
        row["delivery_rate"] = rate(row["delivered_count"], row["sent_count"])
        row["read_rate"] = rate(row["read_count"], row["delivered_count"])
        row["reply_rate"] = rate(row["replied_count"], row["delivered_count"])
        results.append(row)
    return {"range": rng.as_dict(), "results": results}


# --- team --------------------------------------------------------------------------------------


def team(workspace, rng: ReportRange) -> dict:
    members = Membership.objects.filter(workspace=workspace).values_list(
        "user_id", "user__full_name", "user__email", "role"
    )
    sent = dict(
        messages_in(workspace, rng.start, rng.end)
        .filter(direction=OUTBOUND, source=Message.Source.INBOX, sent_by__isnull=False)
        .values("sent_by")
        .annotate(count=Count("pk"))
        .order_by()
        .values_list("sent_by", "count")
    )
    conversations = {
        assignee: (assigned, closed)
        for assignee, assigned, closed in Conversation.objects.filter(
            workspace=workspace, assignee__isnull=False
        )
        .filter(_in("last_message_at", rng.start, rng.end))
        .values("assignee")
        .annotate(
            assigned=Count("pk"),
            closed=Count("pk", filter=Q(status=Conversation.Status.CLOSED)),
        )
        .order_by()
        .values_list("assignee", "assigned", "closed")
    }
    results = []
    for user_id, full_name, email, role in members:
        assigned, closed = conversations.get(user_id, (0, 0))
        results.append(
            {
                "user_id": user_id,
                "name": full_name or email,
                "email": email,
                "role": role,
                "messages_sent": sent.get(user_id, 0),
                "conversations_assigned": assigned,
                "conversations_closed": closed,
            }
        )
    results.sort(key=lambda row: (-row["messages_sent"], row["name"].lower(), row["email"]))
    return {"range": rng.as_dict(), "results": results}


# --- commerce ----------------------------------------------------------------------------------


def commerce(workspace, rng: ReportRange) -> dict:
    orders = orders_in(workspace, rng.start, rng.end)
    paid = Q(payment_status__in=PAID_STATUSES)
    daily = (
        orders.annotate(day=TruncDate("created_at", tzinfo=rng.zone))
        .values("day")
        .annotate(
            orders=Count("pk"),
            paid_orders=Count("pk", filter=paid),
            revenue_paise=Coalesce(Sum("total_paise", filter=paid), 0),
        )
        .order_by("day")
    )
    by_day = {row["day"]: row for row in daily}
    series = []
    order_count = paid_count = revenue = 0
    for day in rng.dates():
        row = by_day.get(day)
        point = {
            "date": day,
            "orders": row["orders"] if row else 0,
            "revenue_paise": row["revenue_paise"] if row else 0,
        }
        order_count += point["orders"]
        revenue += point["revenue_paise"]
        paid_count += row["paid_orders"] if row else 0
        series.append(point)

    by_status = orders.values("status").annotate(count=Count("pk")).order_by("-count", "status")
    by_payment_method = (
        orders.values("payment_method")
        .annotate(
            orders=Count("pk"),
            revenue_paise=Coalesce(Sum("total_paise", filter=paid), 0),
        )
        .order_by("-orders", "payment_method")
    )
    return {
        "range": rng.as_dict(),
        "series": series,
        "orders": order_count,
        "paid_orders": paid_count,
        "revenue_paise": revenue,
        "average_order_paise": revenue // paid_count if paid_count else None,
        "by_status": [dict(row) for row in by_status],
        "by_payment_method": [dict(row) for row in by_payment_method],
        "top_products": top_products(workspace, rng),
    }


def top_products(workspace, rng: ReportRange) -> list[dict]:
    items = (
        OrderItem.objects.filter(
            workspace=workspace,
            order__created_at__gte=rng.start,
            order__created_at__lt=rng.end,
            order__payment_status__in=PAID_STATUSES,
        )
        .exclude(order__status=Order.Status.DRAFT)
        .order_by()
    )
    totals = {"quantity": Sum("quantity"), "revenue_paise": Sum("line_total_paise")}
    # Items keep their product when it still exists; deleted products are grouped by name.
    with_product = (
        items.filter(product__isnull=False)
        .values("product_id")
        .annotate(name=Max("name"), **totals)
        .order_by("-revenue_paise", "name")[:TOP_PRODUCTS]
    )
    without_product = (
        items.filter(product__isnull=True)
        .values("name")
        .annotate(**totals)
        .order_by("-revenue_paise", "name")[:TOP_PRODUCTS]
    )
    rows = [dict(row) for row in with_product]
    rows += [{"product_id": None, **row} for row in without_product]
    rows.sort(key=lambda row: (-row["revenue_paise"], row["name"]))
    return rows[:TOP_PRODUCTS]
