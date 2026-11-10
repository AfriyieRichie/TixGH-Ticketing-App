from celery import shared_task

from apps.events.models import Event

from . import refunds  # noqa: F401 - module import (refunds imports this module too)
from .models import Refund


@shared_task
def process_refund_task(refund_id: int) -> None:
    if r := Refund.objects.filter(pk=refund_id).first():
        refunds.process_refund(r)


@shared_task
def refund_cancelled_event_task(event_id: int) -> int:
    event = Event.objects.filter(pk=event_id).first()
    return refunds.refund_cancelled_event(event) if event else 0
