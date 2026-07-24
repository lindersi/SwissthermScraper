# x-center x40 — local connection notes

Notes from probing the PZP / Kermi heat-pump controller on the LAN (Jul 2026).

## Device

| | |
|---|---|
| LAN IP | `192.168.1.198` |
| MAC | `00:07:8E:22:ED:0D` (Garz & Fricke HMI) |
| Controller | **x-center x40** (Telnet banner: `Windows CE Telnet Service on XCenter40`) |
| Branding | PZP (Czech), software stack shared with Kermi x-center |

## Port scan result

| Port | Service | Status |
|---|---|---|
| 21 | FTP | Open (`220 Service ready…`, no anonymous login) |
| 23 | Telnet | Open (WinCE login prompt) |
| 22 | SSH | Closed |
| 80 / 443 | HTTP(S) | Closed |
| 502 | Modbus TCP | Closed |

Ping works; there is **no local HTTP or Modbus TCP** listener on this unit. FTP/Telnet are service ports on the panel OS, not a documented datapoint API.

This matches other x40 owners without an Interface Module (IFM): only 21/23 open, cloud RemoteControl for the UI.

## Where to find HTTP protocol settings (on the panel)

1. Open the system / context menu → **Expertenlogin** (“Experte anmelden”).
2. Password: **`Full`**
3. Check **Einstellungen → Protokolle** / **Protokolleinstellungen** for an **HTTP** entry.
4. Also useful: **Einstellungen → Netzwerk → HomeLan** (LAN/IP only — not the HTTP server).

If HTTP is missing and cannot be added, local HTTP is likely unsupported on this hardware (no IFM). Ask PZP / installer / Kermi support.

## Options for reading data

1. **Local HTTP** (if IFM / protocol available) — e.g. `POST /api/Security/Login`, favorites / datapoint APIs; Python: [`kermi-xcenter`](https://pypi.org/project/kermi-xcenter/). Password is often the last 4 digits of the serial number.
2. **Modbus** — TCP (port 502) usually needs IFM + activation; some x40 setups use **Modbus RTU** via RS485 + Ethernet converter instead.
3. **Cloud portal** (current StScraper approach) — Selenium against RemoteControl, or a JSON/API client such as [hacs-krmi-xcntr](https://github.com/afmklk/hacs-krmi-xcntr).

### Portal JSON API (this repo)

Production client: repo-root [`portal_api_client.py`](../portal_api_client.py)
(wired from `app.py`). Maps datapoints to the **same** MQTT keys
(`swisstherm/Aussentemp.`, `swisstherm/COP`, …; flat `swisstherm_s0_leistung`).

```bash
pip install -r requirements.txt
python portal_api_client.py discover   # calibrate DatapointConfigId map
python portal_api_client.py once         # print Heizkreis dict
python portal_api_client.py once --mqtt  # publish swisstherm/* once
python app.py                            # full MQTT control loop
```

## References

- [evcc #22565](https://github.com/evcc-io/evcc/issues/22565) — x40 HTTP / protocol settings discussion
- [HA thread](https://community.home-assistant.io/t/kermi-heat-pump-x-center-integration-kind-of-without-modbus/848633) — local API vs cloud-only x40
- [py-kermi-xcenter](https://github.com/jr42/py-kermi-xcenter) — local HTTP + Modbus client
