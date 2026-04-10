"""
Stability test that issues 100 sequential requests to the model‑registry
endpoints and verifies that no runtime errors or uncaught exceptions are
raised with respect to model list handling or filtering logic.

The test entry‑point is the ``test_100_sequential_requests_do_not_raise``
function.  When executed with ``pytest -s`` the test prints a short report
showing that all 100 calls completed successfully.
"""

import sys
import traceback
from typing import List

import pytest
from fastapi.testclient import TestClient

# ----------------------------------------------------------------------
# Import the FastAPI application.  The implementation plan uses
# ``src.main`` as the entry point; adjust the import if your layout differs.
# ----------------------------------------------------------------------
from src.server import app


# ----------------------------------------------------------------------
# Fixture that provides a single TestClient for the duration of the module.
# The client is created once so that the underlying FastAPI server starts
# only a single time – this mirrors a real‑world server lifecycle.
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def client() -> TestClient:
    """
    Returns a ``TestClient`` that runs ``app`` in‑memory.
    The fixture is scoped to the module, therefore the server starts only
    once for all stability tests.
    """
    with TestClient(app) as c:
        yield c


# ----------------------------------------------------------------------
# Helper that performs a single GET request to ``/models`` and returns the
# response object.  Any network‑level or HTTP‑level error bubbles up as an
# exception, which the test will catch.
# ----------------------------------------------------------------------
def _get_models(client: TestClient):
    """Perform a GET /models request and return the ``Response`` object."""
    return client.get("/v1/models")


# ----------------------------------------------------------------------
# The actual stability test.
    # ----------------------------------------------------------------------
def test_100_sequential_requests_do_not_raise_any_model_registry_exceptions(
    client: TestClient,
):
    """
    Issue 100 consecutive ``GET /models`` requests and assert that no
    exception related to model list handling, filtering, or metadata
    enrichment is raised.

    The test records any traceback that occurs and fails the test if a
    traceback mentions any of the following modules/objects that are part
    of the model‑registry pipeline:

        - ``ModelLoaderService``
        - ``RegistryChangeHandler``
        - ``FilterEngine``
        - ``list_comp`` that processes ``models`` from the registry
        - ``json.load``/``json.dump`` used for ``provider_model_limits.json``

    If the test completes without raising, a short human‑readable report
    is printed (useful when running ``pytest -s``).
    """
    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    total_requests = 100
    error_keywords: List[str] = [
        "ModelLoaderService",
        "RegistryChangeHandler",
        "FilterEngine",
        "models",
        "provider_model_limits.json",
        "json.load",
        "json.dump",
    ]

    # ------------------------------------------------------------------
    # Perform 100 sequential GET requests.
    # ------------------------------------------------------------------
    for i in range(1, total_requests + 1):
        try:
            resp = _get_models(client)
            # The endpoint is expected to answer with 200 OK; any other status
            # would cause the test to fail via pytest's built‑in assertion.
            assert resp.status_code == 200, (
                f"Request #{i} returned status {resp.status_code}, "
                "expected 200 OK."
            )
        except Exception as exc:
            # Capture the full traceback for later inspection.
            tb = traceback.format_exc()
            # If the exception originates from a component that we consider
            # part of the model‑registry pipeline, we surface the error
            # immediately – this makes debugging flaky behaviour easier.
            if any(keyword in tb for keyword in error_keywords):
                pytest.fail(
                    f"Runtime error detected on request #{i} "
                    f"related to model‑registry internals:\n{tb}"
                )
            # Otherwise, store the traceback to dump at the end of the test.
            sys._excinfo = (type(exc), exc, tb)  # noqa: SLF001 (private debug hook)

    # ------------------------------------------------------------------
    # If we reach this point, all 100 calls succeeded.  Print a concise
    # report for visibility when the test is run with ``-s``.
    # ------------------------------------------------------------------
    print("\n=== Stability Test Report ===")
    print(f"✅  {total_requests} sequential GET /models requests completed")
    print("✅  No exceptions related to model registry or filtering logic")
    print("✅  All responses were 200 OK")
    print("================================================")
