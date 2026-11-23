"""Bearer-token gate: optional, loopback-safe, with public health checks."""

import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from src.auth import BearerAuthMiddleware


def build_client(token: str) -> TestClient:
    app = FastAPI()
    app.add_middleware(BearerAuthMiddleware, token=token)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def health():
        return {"status": "healthy"}

    @app.get("/health")
    def health_detail():
        return {"status": "healthy"}

    @app.get("/v1/models")
    def models():
        return {"object": "list", "data": []}

    return TestClient(app)


class TestBearerAuthMiddleware(unittest.TestCase):
    def test_disabled_token_allows_all_requests(self):
        client = build_client("")
        self.assertEqual(client.get("/v1/models").status_code, 200)

    def test_missing_token_is_rejected_with_envelope(self):
        client = build_client("secret")
        response = client.get("/v1/models")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"]["type"], "authentication_error"
        )
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_wrong_scheme_and_wrong_token_are_rejected(self):
        client = build_client("secret")
        self.assertEqual(
            client.get("/v1/models", headers={"Authorization": "Basic secret"}).status_code,
            401,
        )
        self.assertEqual(
            client.get("/v1/models", headers={"Authorization": "Bearer nope"}).status_code,
            401,
        )

    def test_correct_token_is_accepted(self):
        client = build_client("secret")
        response = client.get(
            "/v1/models", headers={"Authorization": "Bearer secret"}
        )
        self.assertEqual(response.status_code, 200)

    def test_health_and_preflight_remain_public(self):
        client = build_client("secret")
        self.assertEqual(client.get("/").status_code, 200)
        self.assertEqual(client.get("/health").status_code, 200)
        response = client.options(
            "/v1/models",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
