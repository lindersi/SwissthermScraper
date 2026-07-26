"""
Swisstherm / Grünenwald / Kermi heat-pump scraper.

Fetches Heizkreis and energy-counter values via the portal JSON API and
publishes to MQTT for Home Assistant (no Selenium).
"""

from __future__ import annotations

import datetime
import socket
import sys
import time
import traceback

import paho.mqtt.client as mqtt

import energy
import portal_api_client
import secrets

# ------------------------------------------------------
# MQTT control state (mutated from on_message)
control = {
    "onoff": "",
    "delay": 30,  # seconds between scrapes
    "waittime": 15,  # minutes between reconnect attempts
    "retries": 50,  # reconnect attempts before exit
}


LWT_TOPIC = "swisstherm/LWT"
LWT_ONLINE = "online"
LWT_OFFLINE = "offline"


def on_connect(client, userdata, flags, reason_code, properties=None):
    # Compatible with paho-mqtt 2.x CallbackAPIVersion.VERSION2
    print(f"MQTT connected with result code {reason_code}")
    # Birth message (retained). Broker publishes LWT_OFFLINE on unclean disconnect.
    client.publish(LWT_TOPIC, payload=LWT_ONLINE, qos=1, retain=True)
    client.subscribe("swisstherm/control/#")


def on_message(client, userdata, msg):
    received = msg.payload.decode("utf-8")
    print(f"{msg.topic} {received}")

    if msg.topic == "swisstherm/control/zaehler" and received == "get":
        client.publish("swisstherm/status", payload="Abruf Energiezähler ausgelöst")
        energy.energiezaehler(None, client)
    elif msg.topic == "swisstherm/control/onoff":
        control["onoff"] = received
    elif msg.topic == "swisstherm/control/delay":
        control["delay"] = int(received)
    elif msg.topic == "swisstherm/control/waittime":
        control["waittime"] = int(received)
    elif msg.topic == "swisstherm/control/retries":
        control["retries"] = int(received)


def publish_status(client, payload: str) -> None:
    client.publish("swisstherm/status", payload=payload)


def publish_lwt(client, payload: str) -> None:
    client.publish(LWT_TOPIC, payload=payload, qos=1, retain=True)


def create_mqtt_client() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.username_pw_set(secrets.mqtt_user, password=secrets.mqtt_pwd)
    # If the process dies or the TCP session drops, the broker publishes offline.
    client.will_set(LWT_TOPIC, payload=LWT_OFFLINE, qos=1, retain=True)
    client.connect(secrets.mqtt_host, secrets.mqtt_port, 60)
    client.loop_start()
    return client


def backoff_minutes(attempt: int) -> float:
    """Short waits for the first few failures, then control['waittime']."""
    if attempt == 1:
        return 0.2
    if attempt < 4:
        return 3.0
    return float(control["waittime"])


def run_scrape_session(client: mqtt.Client, host: str, on_cycle_ok=None) -> None:
    """One API session: login, poll Heizkreis until stop/restart/error."""
    api = portal_api_client.PortalApiClient()
    data: dict = {}
    try:
        api.login()
        print("Laden...", flush=True)
        publish_status(client, "Anmeldung erfolgreich. Seite laden...")

        loop = 0

        while control["onoff"] != "stop":
            if control["onoff"] == "restart":
                control["onoff"] = ""
                raise InterruptedError("Neustart angefordert...")

            if loop > 0:
                # Longer interval when Heizkreis is off
                factor = 4 if data.get("Modus") == "Aus" else 1
                time.sleep(int(control["delay"]) * factor)
            else:
                publish_status(client, "Abfrage gestartet")
            loop += 1

            data = api.fetch_heizkreis()
            for key, value in data.items():
                print(f"{key:16}{value}", flush=True)

            # Note: do NOT treat a static "Zustand seit" as stale.
            # HeatpumpStateLastChanged only updates when WP state changes;
            # in standby it stays frozen for hours — normal for the API path.
            # (The old Selenium check was for a stuck browser session.)

            now = datetime.datetime.now()
            data["Timestamp"] = now
            data["Date"] = now.strftime("%d.%m.%Y")
            data["Time"] = now.strftime("%H:%M:%S")

            for key, value in data.items():
                client.publish(
                    portal_api_client.mqtt_topic_for_key(key),
                    payload=str(value).replace(",", "."),
                )

            publish_status(
                client,
                f"Loop {loop}, {len(data)} items sent from {host}, "
                f"delay={control['delay']}s",
            )
            print(f"Loop {loop} OK, {len(data)} items", flush=True)
            if on_cycle_ok:
                on_cycle_ok()

    finally:
        pass


def main() -> int:
    host = socket.gethostname()
    client = create_mqtt_client()
    publish_status(
        client,
        f"Swisstherm-Scraper gestartet auf {host}, "
        f"Abrufintervall (delay): {control['delay']}s, "
        f"source=portal-api",
    )

    attempt = 0
    max_retries = int(control["retries"])
    exit_code = 0

    def reset_attempts():
        nonlocal attempt
        attempt = 0

    try:
        while attempt < max_retries:
            if control["onoff"] == "stop":
                break

            if attempt > 0:
                wait_min = backoff_minutes(attempt)
                publish_status(client, f"Abrufversuch {attempt}: Warte {wait_min} min ...")
                time.sleep(wait_min * 60)

            attempt += 1
            try:
                run_scrape_session(client, host, on_cycle_ok=reset_attempts)
                break  # clean stop from inner loop
            except KeyboardInterrupt:
                publish_status(client, "Abruf der Swisstherm-Heizkreisdaten manuell abgebrochen")
                exit_code = 0
                break
            except InterruptedError as exc:
                print(f"Neustart: {exc}")
                publish_status(client, f"Neustart: {exc}")
                attempt = 0
            except Exception:
                print(
                    f"Fehler beim Abruf (Versuch {attempt}): "
                    f"{sys.exc_info()[0].__name__}: {sys.exc_info()[1]}"
                )
                print(traceback.format_exc(limit=3))
                publish_status(
                    client,
                    f"Fehler beim Abruf der Swisstherm-Heizkreisdaten "
                    f"(Versuch {attempt}): {sys.exc_info()[1]}",
                )
        else:
            publish_status(
                client,
                f"Notify: Max. Versuche ({max_retries}) erreicht — Beende.",
            )
            exit_code = 1

    finally:
        print("Abruf Swisstherm-Heizkreisdaten wurde beendet.")
        publish_status(
            client,
            f"Notify: Abruf Swisstherm-Heizkreisdaten von {host} wurde beendet.",
        )
        # Clean shutdown: clear LWT ourselves (broker would not fire will).
        publish_lwt(client, LWT_OFFLINE)
        time.sleep(0.2)  # let the offline publish flush
        client.loop_stop()
        client.disconnect()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
