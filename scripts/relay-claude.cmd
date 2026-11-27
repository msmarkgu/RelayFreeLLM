@echo off
REM Launch Claude Code against a locally running RelayFreeLLM Anthropic endpoint.
REM Start the gateway separately with: python -m src.server
REM RELAY_AUTH_TOKEN is read from .env or the environment by both the server
REM and this script, so set it in one place. An explicitly empty value disables
REM auth; Claude Code still receives a placeholder credential.

if not defined RELAY_AUTH_TOKEN if exist .env (
    for /F "tokens=1,* delims==" %%A in (.env) do (
        if "%%A"=="RELAY_AUTH_TOKEN" set "RELAY_AUTH_TOKEN=%%B"
    )
)

set PORT=%PORT%
if "%PORT%"=="" set PORT=8000
set ANTHROPIC_BASE_URL=http://127.0.0.1:%PORT%
set ANTHROPIC_AUTH_TOKEN=%RELAY_AUTH_TOKEN%
if "%ANTHROPIC_AUTH_TOKEN%"=="" set ANTHROPIC_AUTH_TOKEN=relay-free
set ANTHROPIC_MODEL=%CLAUDE_MODEL%
if "%ANTHROPIC_MODEL%"=="" set ANTHROPIC_MODEL=claude-sonnet-5-5

set CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST=1
set CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1
set CLAUDE_CODE_AUTO_MODE_SERVER=0
set CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1
set CLAUDE_CODE_AUTO_COMPACT_WINDOW=%CLAUDE_CODE_AUTO_COMPACT_WINDOW%
if "%CLAUDE_CODE_AUTO_COMPACT_WINDOW%"=="" set CLAUDE_CODE_AUTO_COMPACT_WINDOW=200000

set CLAUDE_ENABLE_STREAM_WATCHDOG=0
set CLAUDE_ENABLE_BYTE_WATCHDOG=0
set API_FORCE_IDLE_TIMEOUT=0
set API_TIMEOUT_MS=2147483647

claude %*
