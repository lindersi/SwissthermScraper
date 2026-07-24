"""Shared Chrome/Selenium setup for Windows (dev) and Linux (prod).

Uses Selenium Manager (built into Selenium 4.6+) so chromedriver no longer
needs to be installed or matched manually. Headless mode is controlled by
STSCRAPER_HEADLESS (1/0/true/false). If unset: headless on Linux, headed on Windows.
"""

from __future__ import annotations

import os
import platform
import sys

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


def _env_flag(name: str) -> bool | None:
    value = os.environ.get(name)
    if value is None:
        return None
    return value.strip().lower() in ("1", "true", "yes", "on")


def should_run_headless() -> bool:
    override = _env_flag("STSCRAPER_HEADLESS")
    if override is not None:
        return override
    # Prod (Elitebook/Linux) typically has no display; Windows dev wants a window.
    return platform.system() != "Windows"


def create_chrome_options(headless: bool | None = None) -> Options:
    if headless is None:
        headless = should_run_headless()

    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1024,768")
    options.add_argument("--disable-extensions")
    options.add_argument("--ignore-certificate-errors")
    # Avoid leftover proxy / automation quirks on some hosts
    options.add_argument("--proxy-server=direct://")
    options.add_argument("--proxy-bypass-list=*")

    if headless:
        # new headless is more compatible with modern Chrome
        options.add_argument("--headless=new")
    else:
        options.add_argument("--start-maximized")

    binary = os.environ.get("STSCRAPER_CHROME_BINARY")
    if binary:
        options.binary_location = binary

    return options


def create_driver(options: Options | None = None) -> webdriver.Chrome:
    """Create a Chrome WebDriver via Selenium Manager (no manual chromedriver path)."""
    if options is None:
        options = create_chrome_options()

    # Explicit Service() still lets Selenium Manager resolve the driver binary.
    service = Service()
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(60)
    return driver


def quit_driver(driver) -> None:
    """Best-effort driver shutdown (quit > close)."""
    if driver is None:
        return
    try:
        driver.quit()
    except Exception as exc:  # noqa: BLE001 - cleanup must not raise
        print(f"Chrome konnte nicht beendet werden: {exc}", file=sys.stderr)
