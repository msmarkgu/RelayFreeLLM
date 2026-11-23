"""Optional bearer-token authentication for the local gateway.

The gateway binds to loopback by default, but other local processes can still
reach it. Setting ``RELAY_AUTH_TOKEN`` closes that gap: every API/admin request
must present the token, while ``/`` and ``/health`` remain public for readiness
probes and harness launchers.
"""

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

PUBLIC_PATHS = frozenset({"/", "/health"})


def _unauthorized() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "error": {
                "message": "Missing or invalid bearer token.",
                "type": "authentication_error",
            }
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Reject requests without a matching bearer token when one is configured."""

    def __init__(self, app, token: str = ""):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request, call_next):
        if (
            not self.token
            or request.method == "OPTIONS"
            or request.url.path in PUBLIC_PATHS
        ):
            return await call_next(request)

        header = request.headers.get("authorization", "")
        scheme, _, supplied = header.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            supplied.strip(), self.token
        ):
            return _unauthorized()

        return await call_next(request)
