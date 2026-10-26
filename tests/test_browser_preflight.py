"""Preflight checks the real visitor runtime, including headless-shell installs."""
import pytest
from playwright.sync_api import BrowserType, Error

from sim.app_swarm import BROWSER_INSTALL, require_browser


def test_headless_runtime_works_without_reading_full_browser_path(monkeypatch):
    def unavailable_full_browser(self):
        raise AssertionError('The full browser path does not describe headless readiness')

    monkeypatch.setattr(BrowserType, 'executable_path', property(unavailable_full_browser))
    # A real browser starts and closes; no model, network or user browser involved.
    assert require_browser()


def test_failed_real_launch_stops_before_visitors_with_repair_instruction(monkeypatch):
    def failed_launch(self, **kwargs):
        assert kwargs == {'headless': True}
        raise Error('headless shell cannot start')

    monkeypatch.setattr(BrowserType, 'launch', failed_launch)
    with pytest.raises(ValueError, match='headless shell cannot start') as error:
        require_browser()
    assert BROWSER_INSTALL in str(error.value)
