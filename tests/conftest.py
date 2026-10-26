import pytest


def pytest_sessionstart(session):
    """A fresh clone without Chromium gets the one line that names the install command, not a Playwright traceback per browser test."""
    from sim import app_swarm
    try: app_swarm.require_browser()
    except ValueError as missing: pytest.exit(str(missing), returncode=1)
