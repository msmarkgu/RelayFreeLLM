"""Optional bearer-token authentication for the local gateway.

The gateway binds to loopback by default, but other local processes can still
reach it. Setting ``RELAY_AUTH_TOKEN`` closes that gap: every API/admin request
must present the token, while ``/``, ``/health`` and ``/v1/models`` remain
public. The model list contains no secrets and Claude Code discovers its aliases
through ``/v1/models`` before it has a chance to send an auth header.
"""

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

PUBLIC_PATHS = frozenset({"/", "/health", "/v1/models"})


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
