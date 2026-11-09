"""Offline auth regression: unittest runner, no server/database imports.

Run with PYTHONPATH=src using the existing environment. TestClient uses ASGI
in-process, not HTTP sockets. Only synthetic keys are used.
"""
import os
import unittest
from unittest.mock import patch

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from tradememory.auth import BearerAuthMiddleware, require_auth


class TenantGuardTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"TRADEMEMORY_API_KEYS": "test-a:one,test-b:two"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.called = []
        app = FastAPI()
        app.add_middleware(BearerAuthMiddleware)

        @app.api_route("/protected", methods=["GET", "POST"])
        def protected(request: Request):
            self.called.append(True)
            return {"tenant": request.state.auth.tenant_id}

        @app.get("/health")
        def health():
            return {"ok": True}

        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_distinct_tenants_block_valid_missing_and_invalid_tokens(self):
        for method in ("GET", "POST"):
            for headers in ({}, {"Authorization": "Bearer test-a"},
                            {"Authorization": "Bearer test-b"},
                            {"Authorization": "Bearer invalid"}):
                with self.subTest(method=method, headers=headers):
                    response = self.client.request(method, "/protected", headers=headers)
                    self.assertEqual(response.status_code, 503)
                    self.assertIn("separate process and database", response.json()["detail"])
        self.assertEqual(self.called, [])

    def test_health_remains_available(self):
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_multiple_keys_same_tenant_remain_supported(self):
        with patch.dict(os.environ, {"TRADEMEMORY_API_KEYS": "test-a:one,test-b:one"}):
            for key in ("test-a", "test-b"):
                response = self.client.get("/protected", headers={"Authorization": f"Bearer {key}"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"tenant": "one"})
            self.assertEqual(self.client.get("/protected").status_code, 401)

    def test_open_mode_preserved(self):
        with patch.dict(os.environ, {"TRADEMEMORY_API_KEYS": ""}):
            self.assertEqual(self.client.get("/protected").json(), {"tenant": "default"})

    def test_guard_rechecks_configuration_per_request(self):
        with patch.dict(os.environ, {"TRADEMEMORY_API_KEYS": "test-a:one"}):
            self.assertEqual(self.client.get("/protected", headers={"Authorization": "Bearer test-a"}).status_code, 200)
        self.assertEqual(self.client.get("/protected", headers={"Authorization": "Bearer test-a"}).status_code, 503)

    def test_dependency_also_fails_closed(self):
        app = FastAPI()

        @app.get("/protected")
        def protected(auth=Depends(require_auth)):
            self.called.append(True)
            return {"tenant": auth.tenant_id}

        with TestClient(app) as client:
            response = client.get("/protected", headers={"Authorization": "Bearer test-a"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.called, [])


if __name__ == "__main__":
    unittest.main()
