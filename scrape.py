"""Parse heat-circuit overview DOM into a flat dict for MQTT publish."""

from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver


OVERLAY_KEYS = [
    "Heizkreis",
    "Vorlauf Soll",
    "Vorlauf Ist",
    "Mischer",
    "Modus",
    "Ventil",
    "WP Rückl.",
    "WP Vorl.",
    "WP Umwälz",
    "WP UW Öffn",
    "WP UW Hyst",
    "WP UW Flow",
    "TWE Soll",
    "TWE Ist",
    "TWE Hyst",
    "Puffer Soll",
    "Puffer Ist",
    "Puffer Hyst",
]


def scrape_heizkreis(driver: WebDriver) -> dict:
    """Read current Heizkreis overview values from the loaded portal page.

    Raises ConnectionError when the portal layout/state looks inconsistent
    (e.g. transition back into heating mode) so the caller can restart.
    """
    data: dict = {}

    values = driver.find_elements(
        By.CSS_SELECTOR,
        "div.appContainer div.component-container > div > div > div",
    )

    linke_zeilen = values[0].text.split("\n")
    heizleistung = linke_zeilen[0].split(": ")
    hl = heizleistung[1].split(" ")[0]
    data[heizleistung[0]] = 0 if hl == "-" else hl

    cop = linke_zeilen[1].split(": ")
    data[cop[0]] = cop[1]

    data["Zustand seit"] = values[1].text.strip()

    rechte_zeilen = values[2].text.split("\n")
    aussentemp = rechte_zeilen[0].split(": ")
    data[aussentemp[0].replace("Außentemperatur", "Aussentemp.")] = aussentemp[1].split(" ")[0]
    wpzustand = rechte_zeilen[1].split(": ")
    data[wpzustand[0].replace("Wärmepumpenzustand", "WP-Zustand")] = wpzustand[1]

    overlay = driver.find_elements(By.CSS_SELECTOR, "div.overlay span")
    keys = list(OVERLAY_KEYS)

    modus = overlay[2].text.split(" ")[0]
    if modus == "Aus":
        # Vorlauf Soll/Ist are missing from the overview when Heizkreis is off
        del keys[1:3]
    elif overlay[4].text.split(" ")[0] != "Heizen":
        raise ConnectionError("Datenzuweisung fehlerhaft - Neustart...")

    for i, key in enumerate(keys):
        data[key] = overlay[i].text.split(" ")[0]
        print(f"{key:16}{data[key]}")

    return data
