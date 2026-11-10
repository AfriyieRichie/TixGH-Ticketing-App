from celery import shared_task

from apps.payments.refunds import check_refunds

from . import services


@shared_task
def run_growth_jobs() -> dict:
    return {"campaign_emails": services.process_campaigns(), "review_requests": services.send_review_requests(),
            "refunds": check_refunds()}
