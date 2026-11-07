"""
Run a background task without slowing down the request that triggered it.

- With a Celery worker (CELERY_TASK_ALWAYS_EAGER=False): queue it as usual.
- Without one (free hosting): run it in a background thread, so sending an
  email or SMS never delays a buyer's checkout or confirmation page.
- In tests: run it inline, so results can be asserted immediately.
"""

import logging
import threading

from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)


def dispatch(task, *args):
    if not settings.CELERY_TASK_ALWAYS_EAGER:
        task.delay(*args)
    elif getattr(settings, "TESTING", False):
        task(*args)
    else:
        threading.Thread(target=_run, args=(task, args), daemon=True).start()


def _run(task, args):
    try:
        task(*args)
    except Exception:
        logger.exception("Background task %s failed", getattr(task, "name", task))
    finally:
        connection.close()  # threads get their own DB connection; release it
