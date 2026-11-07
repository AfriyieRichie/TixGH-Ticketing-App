import base64
import threading
from unittest.mock import MagicMock, patch

from django.core.mail import EmailMultiAlternatives, get_connection
from django.test import SimpleTestCase, override_settings

from apps.core import dispatch as dispatch_mod


@override_settings(BREVO_API_KEY="xkeysib-test", DEFAULT_FROM_EMAIL="TixGH <sender@example.com>")
class BrevoBackendTests(SimpleTestCase):
    def _connection(self):
        return get_connection("apps.core.email_backends.BrevoAPIBackend")

    @patch("apps.core.email_backends.requests.post")
    def test_payload(self, post):
        post.return_value = MagicMock(status_code=201)
        msg = EmailMultiAlternatives("Your tickets", "plain text", None, ["Ama <ama@example.com>"],
                                     connection=self._connection())
        msg.attach_alternative("<b>html</b>", "text/html")
        msg.attach("ticket.pdf", b"%PDF-1.4 data", "application/pdf")
        self.assertEqual(msg.send(), 1)
        body = post.call_args.kwargs["json"]
        self.assertEqual(post.call_args.kwargs["headers"]["api-key"], "xkeysib-test")
        self.assertEqual(body["sender"], {"email": "sender@example.com", "name": "TixGH"})
        self.assertEqual(body["to"], [{"email": "ama@example.com", "name": "Ama"}])
        self.assertEqual(body["htmlContent"], "<b>html</b>")
        self.assertEqual(body["textContent"], "plain text")
        self.assertEqual(base64.b64decode(body["attachment"][0]["content"]), b"%PDF-1.4 data")

    @patch("apps.core.email_backends.requests.post")
    def test_error_raises_unless_silent(self, post):
        post.return_value = MagicMock(status_code=401, text="unauthorized")
        msg = EmailMultiAlternatives("s", "b", None, ["a@example.com"], connection=self._connection())
        with self.assertRaises(RuntimeError):
            msg.send()
        silent = get_connection("apps.core.email_backends.BrevoAPIBackend", fail_silently=True)
        self.assertEqual(silent.send_messages([msg]), 0)


class DispatchTests(SimpleTestCase):
    def test_inline_in_tests(self):
        calls = []
        dispatch_mod.dispatch(lambda x: calls.append(x), 1)
        self.assertEqual(calls, [1])

    @override_settings(TESTING=False, CELERY_TASK_ALWAYS_EAGER=True)
    def test_background_thread_without_worker(self):
        done = threading.Event()
        caller = threading.current_thread()
        seen = {}

        def task(x):
            seen["thread"] = threading.current_thread()
            seen["x"] = x
            done.set()

        with patch.object(dispatch_mod.connection, "close"):
            dispatch_mod.dispatch(task, 7)
            self.assertTrue(done.wait(5))
        self.assertEqual(seen["x"], 7)
        self.assertIsNot(seen["thread"], caller)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_queues_when_worker_exists(self):
        task = MagicMock()
        dispatch_mod.dispatch(task, 3)
        task.delay.assert_called_once_with(3)
