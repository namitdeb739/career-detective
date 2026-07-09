"""Smoke test for the web app module (imports without launching a server)."""

from __future__ import annotations

from career_detective import app


def test_app_has_main() -> None:
    assert callable(app.main)
