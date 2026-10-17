"""What the alerts number sends: platform template definitions and outbound messages.

Every alert is an :class:`Outbound`. It carries the free-form version (the text plus reply
buttons, or a list) and, for alerts, the platform template with the same text, buttons and reply
ids. ``services.deliver`` picks one by the recipient's service window.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apps.inbox.interactive import ListRow, ListSection, list_message, reply_buttons
from apps.orders.models import Order
from common.commerce import build_reply_id

from .models import AlertMessage
from .platform import TEMPLATE_LANGUAGE

Kind = AlertMessage.Kind

ITEM_SUMMARY_MAX_LENGTH = 200
ROW_TITLE_MAX_LENGTH = 24
ROW_DESCRIPTION_MAX_LENGTH = 72
EMPTY_PARAM = "—"
AWB_EXAMPLE = "Delhivery 1234567890 https://www.delhivery.com/track/package/1234567890"

ACTION_TITLES = {"pack": "Mark packed", "ship": "Mark shipped", "cancel": "Cancel"}
# Order transition target -> seller alert action.
TRANSITION_ACTIONS = {"packed": "pack", "shipped": "ship", "cancelled": "cancel"}
# Booking requests: *Accept* confirms the appointment at the start of the requested window.
BOOKING_ACTION_TITLES = {"accept": "Accept", "cancel": "Cancel"}
BOOKING = "booking"
REQUESTED = "requested"
PAY_AT_SHOP = "pay_at_shop"
DEFAULT_TIME_ZONE = "Asia/Kolkata"


# --- Platform templates -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlatformTemplate:
    """A template in UpChatz's WABA (UTILITY, ``en``). ``body`` uses positional variables in
    order; ``buttons`` are quick-reply titles whose payloads are set per send."""

    name: str
    body: str
    body_example: tuple[str, ...]
    buttons: tuple[str, ...] = ()
    category: str = "UTILITY"
    language: str = TEMPLATE_LANGUAGE

    def definition(self) -> dict[str, Any]:
        """The ``create_template`` payload."""
        components: list[dict[str, Any]] = [
            {"type": "BODY", "text": self.body, "example": {"body_text": [list(self.body_example)]}}
        ]
        if self.buttons:
            components.append(
                {
                    "type": "BUTTONS",
                    "buttons": [{"type": "QUICK_REPLY", "text": title} for title in self.buttons],
                }
            )
        return {
            "name": self.name,
            "language": self.language,
            "category": self.category,
            "components": components,
        }

    def matches(self, components: Any) -> bool:
        """Whether Meta's copy has the same body text and quick-reply buttons."""
        if not isinstance(components, list):
            return False
        body = ""
        buttons: list[str] = []
        for component in components:
            if not isinstance(component, Mapping):
                continue
            kind = str(component.get("type", "")).upper()
            if kind == "BODY":
                body = str(component.get("text", ""))
            elif kind == "BUTTONS":
                buttons = [
                    str(button.get("text", ""))
                    for button in component.get("buttons") or []
                    if isinstance(button, Mapping)
                ]
        return body == self.body and tuple(buttons) == self.buttons

    def render(self, params: Sequence[str]) -> str:
        return re.sub(r"\{\{(\d+)\}\}", lambda match: params[int(match.group(1)) - 1], self.body)


SELLER_VERIFY = PlatformTemplate(
    name="upc_seller_verify",
    body=(
        "Hi! {{1}} wants to send order alerts to this WhatsApp number through UpChatz. "
        "Tap Confirm to start getting them."
    ),
    body_example=("Sharma Sweets",),
    buttons=("Confirm",),
)
NEW_ORDER = PlatformTemplate(
    name="upc_new_order",
    body=(
        "New order at {{1}}\n\n"
        "Order: {{2}}\n"
        "Items: {{3}}\n"
        "Total: {{4}}\n"
        "Payment: {{5}}\n\n"
        "Use the buttons below to update the order."
    ),
    body_example=("Sharma Sweets", "SS-1001", "2 x Kaju Katli 250 g", "₹498.00", "Paid online"),
    buttons=(ACTION_TITLES["pack"], ACTION_TITLES["ship"], ACTION_TITLES["cancel"]),
)
ORDER_ATTENTION = PlatformTemplate(
    name="upc_order_attention",
    body=(
        "Order update from {{1}}\n\n"
        "Order {{2}} needs your attention: {{3}}\n\n"
        "Open UpChatz to review it."
    ),
    body_example=("Sharma Sweets", "SS-1001", "the payment arrived after the order expired"),
)
NEW_BOOKING = PlatformTemplate(
    name="upc_new_booking",
    body=(
        "New booking request at {{1}}\n\n"
        "Booking: {{2}}\n"
        "Customer: {{3}}\n"
        "Services: {{4}}\n"
        "Requested: {{5}}\n"
        "Payment: {{6}}\n\n"
        "Tap Accept to confirm it at the start of the requested time, or Cancel to decline it."
    ),
    body_example=(
        "Glow Salon",
        "GS-1001",
        "Priya Sharma",
        "1 x Haircut, 1 x Hair spa",
        "Sat 18 Oct, Morning (09:00-12:00)",
        "Pay at the shop",
    ),
    buttons=(BOOKING_ACTION_TITLES["accept"], BOOKING_ACTION_TITLES["cancel"]),
)
PLATFORM_TEMPLATES = (SELLER_VERIFY, NEW_ORDER, ORDER_ATTENTION, NEW_BOOKING)


# --- Outbound messages --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Outbound:
    kind: str
    body: str
    # Free-form version: a raw Cloud API ``interactive`` object, or None for a text message.
    interactive: Mapping[str, Any] | None = None
    # Template version (alerts only): positional body params and quick-reply payloads in order.
    template: PlatformTemplate | None = None
    template_params: tuple[str, ...] = ()
    button_payloads: tuple[str, ...] = field(default=())

    def free_form_message(self) -> dict[str, Any]:
        if self.interactive is not None:
            return {
                "recipient_type": "individual",
                "type": "interactive",
                "interactive": dict(self.interactive),
            }
        return {
            "recipient_type": "individual",
            "type": "text",
            "text": {"body": self.body, "preview_url": False},
        }

    def template_message(self) -> dict[str, Any]:
        if self.template is None:
            raise ValueError("This message has no template version.")
        components: list[dict[str, Any]] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": param} for param in self.template_params],
            }
        ]
        for index, payload in enumerate(self.button_payloads):
            components.append(
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": str(index),
                    "parameters": [{"type": "payload", "payload": payload}],
                }
            )
        return {
            "recipient_type": "individual",
            "type": "template",
            "template": {
                "name": self.template.name,
                "language": {"code": self.template.language},
                "components": components,
            },
        }


def _template_outbound(
    kind: str,
    template: PlatformTemplate,
    params: Sequence[str],
    buttons: Sequence[tuple[str, str]] = (),
) -> Outbound:
    params = tuple(template_param(param) for param in params)
    body = template.render(params)
    interactive = reply_buttons(body, list(buttons)).interactive if buttons else None
    return Outbound(
        kind=kind,
        body=body,
        interactive=interactive,
        template=template,
        template_params=params,
        button_payloads=tuple(button_id for button_id, _ in buttons),
    )


def _reply(body: str, buttons: Sequence[tuple[str, str]] = ()) -> Outbound:
    interactive = reply_buttons(body, list(buttons)).interactive if buttons else None
    return Outbound(kind=Kind.REPLY, body=body, interactive=interactive)


# --- Formatting helpers -------------------------------------------------------------------------


def template_param(value: object) -> str:
    """Meta rejects template params with newlines, tabs or runs of spaces, or empty ones."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text or EMPTY_PARAM


def truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip(" ,·") + "…"


def format_inr(paise: int) -> str:
    """``145000`` -> ``"₹1,450.00"``; ``12345678`` -> ``"₹1,23,456.78"`` (Indian grouping)."""
    sign = "-" if paise < 0 else ""
    rupees, remainder = divmod(abs(int(paise)), 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])
    return f"{sign}₹{digits}.{remainder:02d}"


def item_summary(order: Order) -> str:
    """``"2 x Kaju Katli 250 g, 1 x Soan Papdi"`` (at most 200 characters)."""
    parts = [
        f"{item.quantity} x {item.name}" for item in order.items.order_by("position", "created_at")
    ]
    summary = ", ".join(parts)
    if not summary:
        count = order.item_count
        summary = f"{count} item" if count == 1 else f"{count} items"
    return truncate(template_param(summary), ITEM_SUMMARY_MAX_LENGTH)


def payment_label(order: Order) -> str:
    if order.payment_method == Order.PaymentMethod.COD:
        return "Cash on delivery"
    if order.payment_method == PAY_AT_SHOP:
        return "Pay at the shop"
    if order.payment_status == Order.PaymentStatus.PAID:
        return "Paid online"
    return "Not paid yet"


def status_label(status: str) -> str:
    try:
        return str(Order.Status(status).label)
    except ValueError:
        return status.replace("_", " ").capitalize()


# --- Bookings -----------------------------------------------------------------------------------


def is_booking(order: Order) -> bool:
    return getattr(order, "kind", "delivery") == BOOKING


def workspace_zone(order: Order) -> ZoneInfo:
    name = getattr(order.workspace, "time_zone", "") or DEFAULT_TIME_ZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIME_ZONE)


def _parse_hhmm(value: object) -> time | None:
    try:
        hours, minutes = str(value).split(":")
        return time(int(hours), int(minutes))
    except (TypeError, ValueError):
        return None


def requested_window(order: Order) -> tuple[str, time, time] | None:
    """The booking's requested window as ``(label, start, end)``, or None when unset."""
    window = getattr(order, "requested_window", None)
    if not isinstance(window, Mapping):
        return None
    start, end = _parse_hhmm(window.get("start")), _parse_hhmm(window.get("end"))
    if start is None or end is None:
        return None
    return str(window.get("label") or "").strip(), start, end


def window_start(order: Order) -> datetime | None:
    """The start of the requested window on the requested day, in the workspace time zone."""
    day = getattr(order, "requested_date", None)
    window = requested_window(order)
    if not isinstance(day, date) or window is None:
        return None
    return datetime.combine(day, window[1], tzinfo=workspace_zone(order))


def format_day(day: date) -> str:
    """``"Sat 18 Oct"``."""
    return f"{day:%a} {day.day} {day:%b}"


def requested_label(order: Order) -> str:
    """``"Sat 18 Oct, Morning (09:00-12:00)"``; "" when the day is unset."""
    day = getattr(order, "requested_date", None)
    if not isinstance(day, date):
        return ""
    window = requested_window(order)
    if window is None:
        return format_day(day)
    label, start, end = window
    span = f"{start:%H:%M}-{end:%H:%M}"
    return f"{format_day(day)}, {label} ({span})" if label else f"{format_day(day)}, {span}"


def appointment_label(order: Order) -> str:
    """``"Sat 18 Oct, 09:00"`` in the workspace time zone; "" when not confirmed."""
    appointment_at = getattr(order, "appointment_at", None)
    if not isinstance(appointment_at, datetime):
        return ""
    return format_local(appointment_at, workspace_zone(order))


def format_local(moment: datetime, zone: ZoneInfo) -> str:
    """``"Sat 18 Oct, 09:00"`` in ``zone``."""
    local = moment.astimezone(zone)
    return f"{format_day(local.date())}, {local:%H:%M}"


def booking_time_label(order: Order) -> str:
    appointment = appointment_label(order)
    return appointment or requested_label(order)


def buyer_name(order: Order) -> str:
    contact = order.contact
    return (contact.name or "").strip() or contact.phone_e164


def order_action_buttons(order: Order) -> list[tuple[str, str]]:
    """Reply buttons for the seller actions the order's status allows: *Accept* on a booking
    request, then pack/ship/cancel in that order."""
    buttons = []
    if (
        is_booking(order)
        and order.status == REQUESTED
        and Order.Status.CONFIRMED in order.allowed_transitions
    ):
        buttons.append((build_reply_id("alerts", "accept", order.pk), "Accept"))
    allowed = {
        TRANSITION_ACTIONS[to] for to in order.allowed_transitions if to in TRANSITION_ACTIONS
    }
    return buttons + [
        (build_reply_id("alerts", action, order.pk), title)
        for action, title in ACTION_TITLES.items()
        if action in allowed
    ]


# --- Alerts -------------------------------------------------------------------------------------


def verification(recipient_id, store_name: str) -> Outbound:
    return _template_outbound(
        Kind.VERIFY,
        SELLER_VERIFY,
        [store_name],
        [(build_reply_id("alerts", "verify", recipient_id), "Confirm")],
    )


def new_order(order: Order, store_name: str) -> Outbound:
    buttons = [
        (build_reply_id("alerts", action, order.pk), title)
        for action, title in ACTION_TITLES.items()
    ]
    params = [
        store_name,
        order.number,
        item_summary(order),
        format_inr(order.total_paise),
        payment_label(order),
    ]
    return _template_outbound(Kind.NEW_ORDER, NEW_ORDER, params, buttons)


def new_booking(order: Order, store_name: str) -> Outbound:
    buttons = [
        (build_reply_id("alerts", action, order.pk), title)
        for action, title in BOOKING_ACTION_TITLES.items()
    ]
    params = [
        store_name,
        order.number,
        buyer_name(order),
        item_summary(order),
        requested_label(order),
        payment_label(order),
    ]
    return _template_outbound(Kind.NEW_BOOKING, NEW_BOOKING, params, buttons)


def needs_attention(order: Order, store_name: str, reason: str) -> Outbound:
    reason = reason or "please check it in UpChatz"
    return _template_outbound(
        Kind.NEEDS_ATTENTION, ORDER_ATTENTION, [store_name, order.number, reason]
    )


def order_cancelled(order: Order, store_name: str, actor: str) -> Outbound:
    """Cancellations by the buyer or the system reuse the attention template (the contract has
    no cancellation template)."""
    who = "the buyer" if actor == "buyer" else "UpChatz"
    reason = f"it was cancelled by {who}"
    if order.cancel_reason:
        reason = f"{reason} ({order.cancel_reason})"
    return _template_outbound(
        Kind.ORDER_CANCELLED, ORDER_ATTENTION, [store_name, order.number, reason]
    )


# --- Command replies ----------------------------------------------------------------------------

HELP_TEXT = (
    "UpChatz order alerts\n\n"
    "Reply with:\n"
    "ORDERS - see your open orders\n"
    "HELP - show this list\n"
    "STOP - stop order alerts\n\n"
    "Use the buttons on an order alert to mark it packed or shipped, or to cancel it. "
    "On a booking request, tap Accept to confirm it."
)


def booking_accepted(order: Order, appointment_at: datetime) -> Outbound:
    when = format_local(appointment_at, workspace_zone(order))
    return text(f"Booking {order.number} is confirmed for {when}. The customer will be told.")


def help_message(prefix: str = "") -> Outbound:
    body = f"{prefix}\n\n{HELP_TEXT}" if prefix else HELP_TEXT
    return _reply(body, [(build_reply_id("alerts", "orders"), "Open orders")])


def text(body: str) -> Outbound:
    return _reply(body)


def verified_confirmation(store_name: str) -> Outbound:
    return help_message(f"You'll now get WhatsApp order alerts for {store_name}.")


def stopped() -> Outbound:
    return text(
        "You won't get order alerts on this number any more. To start again, ask the store "
        "admin to resend the verification from UpChatz."
    )


def stale_option() -> Outbound:
    return help_message("This option is no longer available.")


def cancel_confirmation(order: Order) -> Outbound:
    """Asked after *Cancel*; the order changes only on *Yes, cancel*."""
    question = (
        f"Cancel booking {order.number}? The customer will be told."
        if is_booking(order)
        else f"Cancel order {order.number}? The buyer will be told and items go back to stock."
    )
    return _reply(
        question,
        [
            (build_reply_id("alerts", "cancel_yes", order.pk), "Yes, cancel"),
            (build_reply_id("alerts", "cancel_no", order.pk), "Keep order"),
        ],
    )


def awb_prompt(order: Order) -> Outbound:
    return _reply(
        f"Send the courier and AWB number for order {order.number}, for example:\n"
        f"{AWB_EXAMPLE}\n\nThe tracking link is optional. No courier or AWB? Tap Skip tracking "
        "to mark it shipped without them.",
        [(build_reply_id("alerts", "ship_now", order.pk), "Skip tracking")],
    )


def order_list(orders: Iterable[Order], store_names: Mapping[Any, str]) -> Outbound:
    orders = list(orders)
    if not orders:
        return text("You have no open orders right now.")
    several_stores = len({order.workspace_id for order in orders}) > 1
    rows = []
    for order in orders:
        description = status_label(order.status)
        if is_booking(order) and (when := booking_time_label(order)):
            description = f"{description} · {when}"
        if several_stores:
            description = f"{description} · {store_names.get(order.workspace_id, '')}"
        rows.append(
            ListRow(
                id=build_reply_id("alerts", "orders", order.pk),
                title=truncate(f"{order.number} · {format_inr(order.total_paise)}", 24),
                description=truncate(description, ROW_DESCRIPTION_MAX_LENGTH),
            )
        )
    body = "Your open orders. Pick one to update it."
    content = list_message(body, "View orders", [ListSection(title="", rows=rows)])
    return Outbound(kind=Kind.REPLY, body=body, interactive=content.interactive)


def order_details(order: Order, store_name: str) -> Outbound:
    if is_booking(order):
        lines = [
            f"Booking {order.number} · {store_name}",
            f"Status: {status_label(order.status)}",
            f"Customer: {buyer_name(order)}",
            f"Services: {item_summary(order)}",
        ]
        if appointment := appointment_label(order):
            lines.append(f"Appointment: {appointment}")
        elif requested := requested_label(order):
            lines.append(f"Requested: {requested}")
        lines.append(f"Total: {format_inr(order.total_paise)} ({payment_label(order)})")
        return _reply("\n".join(lines), order_action_buttons(order))
    lines = [
        f"Order {order.number} · {store_name}",
        f"Status: {status_label(order.status)}",
        f"Items: {item_summary(order)}",
        f"Total: {format_inr(order.total_paise)} ({payment_label(order)})",
    ]
    if order.courier_name or order.awb_number:
        lines.append(f"Courier: {order.courier_name} {order.awb_number}".rstrip())
    return _reply("\n".join(lines), order_action_buttons(order))
