"""Recorded upstream-style SSE chunk fixtures shared by gateway contract tests."""

import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "streams"


def load_stream(name: str) -> list[dict]:
    """Load a recorded chunk sequence by fixture name (without .json)."""
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
