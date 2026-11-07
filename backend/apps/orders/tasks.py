from celery import shared_task

from .services import expire_stale_orders


@shared_task
def expire_orders() -> int:
    """Run every minute via Celery beat (see CELERY_BEAT_SCHEDULE)."""
    return expire_stale_orders()
