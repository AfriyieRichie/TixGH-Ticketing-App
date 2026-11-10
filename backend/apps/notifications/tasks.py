from celery import shared_task

from apps.events.models import Event
from apps.orders.models import Order, Ticket
from apps.payments.models import Refund

from . import services


@shared_task
def deliver_order_confirmation(order_id: int) -> None:
    if order := Order.objects.filter(pk=order_id).first():
        services.send_order_confirmation(order)


@shared_task
def deliver_transfer_notice(ticket_id: int, from_name: str) -> None:
    if ticket := Ticket.objects.filter(pk=ticket_id).first():
        services.send_transfer_notice(ticket, from_name)


@shared_task
def deliver_cancellation(event_id: int) -> int:
    event = Event.objects.filter(pk=event_id).first()
    return services.notify_event_cancelled(event) if event else 0


@shared_task
def deliver_refund_notice(refund_id: int) -> None:
    if refund := Refund.objects.select_related("order__event").filter(pk=refund_id).first():
        services.send_refund_notice(refund)


@shared_task
def send_reminders() -> int:
    """Runs hourly via Celery beat."""
    return services.send_due_reminders()
