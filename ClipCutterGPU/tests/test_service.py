"""Real IPv4/IPv6 HTTP regressions without models or a GPU."""
import json
import os
import socket
import unittest
import urllib.error
import urllib.request
from threading import BoundedSemaphore, Thread
from unittest.mock import Mock, patch

from worker import service


class DualStackServiceTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"CLIPCUTTER_WORKER_API_TOKEN": "t" * 32})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.status = patch.dict(service.status, {"ready": False, "state": "warming_up"})
        self.status.start()
        self.addCleanup(self.status.stop)
        # Do not skip IPv6 failures: gateway compatibility is mandatory.
        self.server = service.DualStackHTTPServer(("::", 0), service.Handler)
        self.addCleanup(self.server.server_close)
        self.server.requests = BoundedSemaphore(8)
        self.server.worker = Mock()
        self.server.worker.metrics.return_value = {"active_renders": 0}
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def stop(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.assertFalse(self.thread.is_alive())

    def get(self, host, path, token=None):
        request = urllib.request.Request(
            f"http://{host}:{self.server.server_port}{path}",
            headers={"Authorization": "Bearer " + token} if token else {},
        )
        try:
            response = self.opener.open(request, timeout=3)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, json.load(response)

    def test_health_and_authentication_on_both_address_families(self):
        self.assertEqual(self.server.socket.family, socket.AF_INET6)
        self.assertEqual(self.server.socket.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY), 0)
        for host in ("127.0.0.1", "[::1]"):
            with self.subTest(host=host):
                service.status.update(ready=False, state="warming_up")
                self.assertEqual(self.get(host, "/health/live")[0], 200)
                for path in ("/health", "/health/ready"):
                    code, data = self.get(host, path)
                    self.assertEqual(code, 503)
                    self.assertFalse(data["ready"])
                for token in (None, "wrong"):
                    self.assertEqual(self.get(host, "/api/capabilities", token)[0], 401)
                self.assertEqual(self.get(host, "/api/capabilities", "t" * 32)[0], 200)
                service.status.update(ready=True, state="ready")
                for path in ("/health", "/health/ready"):
                    code, data = self.get(host, path)
                    self.assertEqual(code, 200)
                    self.assertTrue(data["ready"])

    def test_dual_stack_configuration_failure_is_explicit(self):
        server = service.DualStackHTTPServer(("::", 0), service.Handler, bind_and_activate=False)
        self.addCleanup(server.server_close)
        real_socket = server.socket
        server.socket = Mock(wraps=real_socket)
        server.socket.setsockopt.side_effect = OSError("IPv6 unavailable")
        with self.assertRaisesRegex(RuntimeError, "requires IPv4/IPv6 dual-stack"):
            server.server_bind()
        self.assertEqual(real_socket.getsockname()[1], 0)


if __name__ == "__main__":
    unittest.main()
