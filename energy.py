# Sporadic energy-counter fetch; publishes JSON to MQTT (and optionally Google Sheets).

from __future__ import annotations

import json
import traceback

import portal_api_client

# Optional Sheets export lives in playground/gsheet.py (dormant).


def energiezaehler(options, client):
    """Fetch counters via portal JSON API and publish ``swisstherm/zaehler/json``.

    ``options`` is unused (kept for call-site compatibility with the old Selenium path).
    """
    del options  # API path — no Chrome options
    client.publish("swisstherm/status", payload="Abruf Swisstherm-Zählerstände läuft...")
    print("Abruf Swisstherm-Zählerstände läuft...")

    try:
        api = portal_api_client.PortalApiClient()
        api.login()
        data = api.fetch_energy_counters()

        client.publish("swisstherm/zaehler/json", payload=json.dumps(data))
        client.publish("swisstherm/status", payload=f"Zähler abgerufen ({len(data)} Werte).")
        print("Swisstherm-Energiezähler erfolgreich abgerufen.")
        client.publish(
            "swisstherm/status",
            payload="Notify: Swisstherm-Energiezähler erfolgreich abgerufen.",
        )
        # from playground import gsheet; gsheet.main(data, client)

    except Exception as exc:
        print(f"Fehler beim Abruf der Swisstherm-Energiezähler: {exc}")
        print(traceback.format_exc(limit=3))
        client.publish(
            "swisstherm/status",
            payload=f"Notify: Fehler beim Abruf der Swisstherm-Energiezähler: {exc}",
        )


def write_data(data):
    with open("energy-data.txt", "w", encoding="utf-8") as file:
        file.write(json.dumps(data))
