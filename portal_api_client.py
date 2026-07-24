"""
Cloud portal JSON API client (no Selenium for Heizkreis).

Uses the same xcenterpro JSON endpoints as the RemoteControl UI, and maps
datapoints to MQTT keys compatible with app.py:

  swisstherm/<sensor>          — Heizkreis values
  swisstherm_s0_leistung       — flat topic for S0 power (Überschuss S0)
  swisstherm/status            — status strings (app.py)
  swisstherm/zaehler/json      — energy counters (still Selenium via energy.py)
  swisstherm/control/#         — unchanged (app.py)

KPI notes
---------
- COP (swisstherm/COP): only Aktueller COP (HP_TotalCOP); 0 when idle / null.
- SCOP / COP Hz / COP TWE: separate average KPIs — never mixed into COP.
- swisstherm_s0_leistung: S0 power (kW) from portal "S0 Leistung" / ``S0kWh``.

CLI
---
  python portal_api_client.py discover|once|devices
  python portal_api_client.py once --mqtt
"""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import json
import os
import re
import sys
import time
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

try:
    import requests
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Install requests: pip install requests") from exc

import secrets  # repo secrets.py (same as app.py; shadows stdlib when run from project)

# ---------------------------------------------------------------------------
# MQTT sensor names — must stay in sync with scrape.OVERLAY_KEYS + scrape_heizkreis
# ---------------------------------------------------------------------------

MQTT_HEIZKREIS_KEYS = [
    "Heizleistung",
    "COP",
    "SCOP",
    "COP Hz",
    "COP TWE",
    "Verdichteraufnahme",
    "swisstherm_s0_leistung",
    "Zustand seit",
    "Aussentemp.",
    "WP-Zustand",
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

# Human-readable labels (MQTT topic / key stays the left side).
MQTT_HUMAN_NAMES: dict[str, str] = {
    "swisstherm_s0_leistung": "Überschuss S0",
    "COP": "Aktueller COP",
    "SCOP": "Gemittelter COP Hz/TWE",
    "COP Hz": "Gemittelter COP Hz",
    "COP TWE": "Gemittelter COP TWE",
    "Verdichteraufnahme": "Aktuelle Verdichteraufnahme",
    "Heizleistung": "Aktuelle Heizleistung",
}

# DatapointConfigId (UUID) -> MQTT key. Optional override via secrets.portal_datapoint_map.
DATAPOINT_TO_MQTT: dict[str, str] = {
    # No WellKnownName on this point; stable id from GetBundles (x40 DYNAMIC).
    "6fa83c8b-62b5-430d-9855-3582352d17b0": "WP UW Öffn",  # Aktuelle Ventilöffnung
}

# WellKnownName -> MQTT key (x40 / DYNAMIC overview ≈ scrape.OVERLAY_KEYS).
# Calibrated against Menu/GetBundlesByCategory on Grünenwald portal.
WELLKNOWN_TO_MQTT: dict[str, str] = {
    "HP_HeatOutput": "Heizleistung",
    "HP_TotalCOP": "COP",
    "HP_SCOPGesamt": "SCOP",
    "HP_HeatingWaterAverageCOP": "COP Hz",
    "HP_HotWaterAverageCOP": "COP TWE",
    "HP_AktuelleMotorleistungKW": "Verdichteraufnahme",
    "S0kWh": "swisstherm_s0_leistung",
    "HeatpumpStateLastChanged": "Zustand seit",
    "LuftTemperatur": "Aussentemp.",
    "HP_HeatpumpState": "WP-Zustand",
    "MK1Name": "Heizkreis",
    "HP_MK1SollTempPanel": "Vorlauf Soll",
    "HP_MK1IstTemp": "Vorlauf Ist",
    "MK1Ist3WegeVentil": "Mischer",
    "SummerModeHk1": "Modus",
    "HP_StatusUmschaltventilTWE": "Ventil",
    "HP_EinlasstempLadekreis": "WP Rückl.",
    "HP_AuslasstempLadekreis": "WP Vorl.",
    "HP_StatusPO1Ladepumpe": "WP Umwälz",
    "HP_AktuelleSollspreizungPufferladekreis": "WP UW Hyst",
    "HPxyz_DurchflussIstLadekreis": "WP UW Flow",
    "HP_TWESoll": "TWE Soll",
    "HP_TWETempIst": "TWE Ist",
    "HP_EinschalthystereseTWE": "TWE Hyst",
    "HP_Link_AktuellerPuffersollwert": "Puffer Soll",
    "HP_IstTempHW": "Puffer Ist",
    "HP_EinschalthystereseHW": "Puffer Hyst",
}

# Secondary wellknown used only if primary key still missing after first pass.
# Regelsignal = pump drive % (Y1), not valve opening — only if Ventilöffnung absent.
WELLKNOWN_FALLBACK_TO_MQTT: dict[str, str] = {
    "HP_RegelsignalLadepumpe": "WP UW Öffn",
    "HP_RegelsignalPufferladepumpe": "WP UW Öffn",
}

# DisplayName fallbacks when WellKnownName is missing.
NAME_TO_MQTT: dict[str, str] = {
    "Außentemperatur": "Aussentemp.",
    "Aussentemperatur": "Aussentemp.",
    "Aktuelle Heizleistung": "Heizleistung",
    "Aktueller COP": "COP",
    "Gemittelter COP Hz/TWE": "SCOP",
    "Gemittelter COP Hz": "COP Hz",
    "Gemittelter COP TWE": "COP TWE",
    "Aktuelle Verdichteraufnahme": "Verdichteraufnahme",
    "S0 Leistung": "swisstherm_s0_leistung",
    "Status Gesamtanlage": "WP-Zustand",
    "Isttemperatur Vorlauf MK1": "Vorlauf Ist",
    "Solltemperatur Vorlauf MK1": "Vorlauf Soll",
    "Stellung Mischer MK1": "Mischer",
    "Sommerbetrieb MK1": "Modus",
    "Rücklauftemperatur WP": "WP Rückl.",
    "Vorlauftemperatur WP": "WP Vorl.",
    "Pufferladepumpe (WPM-A1 NO8)": "WP Umwälz",
    "Aktuelle Ventilöffnung": "WP UW Öffn",
    "Aktuelle Sollspreizung Pufferladekreis": "WP UW Hyst",
    "Durchfluss WP": "WP UW Flow",
    "Solltemperatur TWE": "TWE Soll",
    "Isttemperatur TWE": "TWE Ist",
    "Einschalthysterese TWE": "TWE Hyst",
    "Aktueller Puffersollwert": "Puffer Soll",
    "Isttemperatur Puffer": "Puffer Ist",
    "Einschalthysterese Hz": "Puffer Hyst",
    "Umschaltventil Heizen/TWE (WPM-A1 NO1)": "Ventil",
}

# Portal overview labels for HP_HeatpumpState (Selenium used these-style strings).
WP_ZUSTAND_LABELS = {
    "Aus": "Aus",
    "Ein-Standby": "Bereitschaft",
    "Ein-HZW": "Heizen",
    "Ein-BWW": "TWE",
    "Ein-Abt": "Abtauen",
    "Aus-EVU": "EVU",
    "Aus-Ala": "Alarm",
    "Kühlen": "Kühlen",
    "Sperrzeit/Kontrollzeit": "Sperrzeit",
}

EXTRA_READ_WELLKNOWN = (
    "HeatpumpStateLastChanged",
    "MK1Name",
    "HP_Link_AktuellerPuffersollwert",
    "HP_TotalCOP",
)

ZERO_UUID = "00000000-0000-0000-0000-000000000000"
USER_AGENT = (
    "Mozilla/5.0 (compatible; StScraper-portal-api/0.1; +local) "
    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
)
OPENID_CLIENT_ID = "XCenterUI"
OPENID_SCOPES = "openid email profile offline_access kermi.xcenter kermi.webcrm"


def _uuid_in(text: str) -> str | None:
    m = re.search(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        text or "",
    )
    return m.group(0) if m else None


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(os.urandom(64)).decode().rstrip("=")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    return verifier, challenge


def _oauth_state() -> str:
    return base64.urlsafe_b64encode(os.urandom(18)).decode().rstrip("=")


def derive_portal_config() -> dict[str, str]:
    """Derive API base + installation/device IDs from existing secrets URLs."""
    login = getattr(secrets, "portal_loginpath", "")
    parsed = urlparse(login)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    api_base = getattr(secrets, "portal_api_base", None) or f"{origin}/xcenterpro/api"
    api_base = api_base.rstrip("/")

    installation_id = getattr(secrets, "portal_installation_id", None) or _uuid_in(login)
    if not installation_id:
        raise ValueError("Could not find installation UUID in portal_loginpath")

    heizkreis = (getattr(secrets, "portal_datapath", {}) or {}).get("Heizkreis", "")
    # .../device/<DEVICE>/OverviewHeatingCircuit/...
    device_id = getattr(secrets, "portal_device_id", None)
    if not device_id and "/device/" in heizkreis:
        device_id = _uuid_in(heizkreis.split("/device/", 1)[1])

    client_id = getattr(secrets, "portal_openid_client_id", None) or OPENID_CLIENT_ID
    scopes = getattr(secrets, "portal_openid_scopes", None) or OPENID_SCOPES
    redirect_uri = (
        getattr(secrets, "portal_openid_redirect_uri", None)
        or f"{origin}/xcenterui/xcenter/auth/loginCallback"
    )

    return {
        "origin": origin,
        "api_base": api_base,
        "installation_id": installation_id,
        "device_id": device_id or ZERO_UUID,
        "login_url": login,
        "openid_authorize": f"{origin}/openid/connect/authorize",
        "openid_token": f"{origin}/openid/connect/token",
        "openid_client_id": client_id,
        "openid_scopes": scopes,
        "openid_redirect_uri": redirect_uri,
    }


def _datapoint_map() -> dict[str, str]:
    custom = getattr(secrets, "portal_datapoint_map", None)
    if isinstance(custom, dict) and custom:
        return {str(k).lower(): str(v) for k, v in custom.items()}
    return {k.lower(): v for k, v in DATAPOINT_TO_MQTT.items()}


class PortalApiClient:
    """Session against the branded xcenterpro cloud API (Grünenwald / Kermi / …)."""

    def __init__(self, cfg: dict[str, str] | None = None):
        self.cfg = cfg or derive_portal_config()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain, */*",
            }
        )
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self._token_expires_at: float = 0.0

    # -- auth -----------------------------------------------------------------

    def login(self) -> None:
        """Authenticate for API calls.

        Prefer OpenID PKCE (current Grünenwald / Kermi portals). Fall back to a
        legacy RemoteControl HTML form if present on portal_loginpath.
        """
        try:
            self._login_openid_pkce()
            return
        except Exception as openid_exc:
            # Legacy path: form on RemoteControl URL (older portals / Selenium path)
            try:
                self._login_remotecontrol_form()
                return
            except Exception as form_exc:
                raise RuntimeError(
                    f"OpenID PKCE failed ({openid_exc}); "
                    f"RemoteControl form login failed ({form_exc})"
                ) from openid_exc

    def _store_tokens(self, tokens: dict[str, Any]) -> None:
        self.access_token = tokens.get("access_token")
        if tokens.get("refresh_token"):
            self.refresh_token = tokens["refresh_token"]
        if not self.access_token:
            raise RuntimeError(f"Token response missing access_token: {tokens!r}")
        # Refresh a minute early; default 1h if expires_in absent.
        expires_in = int(tokens.get("expires_in") or 3600)
        self._token_expires_at = time.monotonic() + max(60, expires_in - 60)

    def ensure_token(self) -> None:
        """Refresh or re-login when the access token is missing/expired."""
        if self.access_token and time.monotonic() < self._token_expires_at:
            return
        if self.refresh_token:
            try:
                self._refresh_access_token()
                return
            except Exception:
                pass
        self.login()

    def _refresh_access_token(self) -> None:
        if not self.refresh_token:
            raise RuntimeError("No refresh_token available")
        token_resp = self.session.post(
            self.cfg["openid_token"],
            data={
                "grant_type": "refresh_token",
                "client_id": self.cfg["openid_client_id"],
                "refresh_token": self.refresh_token,
            },
            timeout=30,
        )
        if not token_resp.ok:
            raise RuntimeError(
                f"Token refresh failed HTTP {token_resp.status_code}: "
                f"{token_resp.text[:300]}"
            )
        self._store_tokens(token_resp.json())

    def _login_openid_pkce(self) -> None:
        """Authorization-code + PKCE with username/password (no browser)."""
        verifier, challenge = _pkce_pair()
        state = _oauth_state()
        params = {
            "client_id": self.cfg["openid_client_id"],
            "redirect_uri": self.cfg["openid_redirect_uri"],
            "response_type": "code",
            "scope": self.cfg["openid_scopes"],
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "ui_locales": "de-DE",
        }
        r = self.session.get(
            self.cfg["openid_authorize"],
            params=params,
            timeout=30,
            allow_redirects=True,
        )
        r.raise_for_status()

        post_url, antiforgery = self._extract_openid_login_form(r)
        if not post_url:
            raise RuntimeError(f"OpenID login form not found at {r.url}")

        posted = self.session.post(
            post_url,
            data={
                "Login": secrets.portal_user,
                "Password": secrets.portal_password,
                "login": "",
                **(
                    {"__RequestVerificationToken": antiforgery}
                    if antiforgery
                    else {}
                ),
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": self.cfg["origin"],
                "Referer": r.url,
            },
            timeout=30,
            allow_redirects=False,
        )

        auth_code = self._follow_redirects_for_code(posted, expected_state=state)
        if not auth_code:
            raise RuntimeError("OpenID login did not return an authorization code")

        token_resp = self.session.post(
            self.cfg["openid_token"],
            data={
                "grant_type": "authorization_code",
                "client_id": self.cfg["openid_client_id"],
                "redirect_uri": self.cfg["openid_redirect_uri"],
                "code": auth_code,
                "code_verifier": verifier,
            },
            timeout=30,
        )
        if not token_resp.ok:
            raise RuntimeError(
                f"Token exchange failed HTTP {token_resp.status_code}: "
                f"{token_resp.text[:300]}"
            )
        self._store_tokens(token_resp.json())

    @staticmethod
    def _extract_openid_login_form(response: requests.Response) -> tuple[str | None, str | None]:
        """Pick the password form (not Entra), return (post_url, antiforgery)."""
        forms = re.findall(
            r'(<form[^>]*action="([^"]*)"[^>]*>.*?</form>)',
            response.text,
            flags=re.I | re.S,
        )
        for html, action in forms:
            if 'id="Login"' in html or 'name="Login"' in html:
                if "LoginEntra" in action:
                    continue
                token_m = re.search(
                    r'name="__RequestVerificationToken"[^>]*value="([^"]+)"',
                    html,
                )
                return urljoin(response.url, action), (
                    token_m.group(1) if token_m else None
                )
        # Fallback: any Login field on the page
        if 'id="Login"' in response.text or 'name="Login"' in response.text:
            token_m = re.search(
                r'name="__RequestVerificationToken"[^>]*value="([^"]+)"',
                response.text,
            )
            action_m = re.search(r'<form[^>]*action="([^"]*)"', response.text, re.I)
            action = action_m.group(1) if action_m else response.url
            return urljoin(response.url, action), (
                token_m.group(1) if token_m else None
            )
        return None, None

    def _follow_redirects_for_code(
        self,
        response: requests.Response,
        expected_state: str,
        max_hops: int = 15,
    ) -> str | None:
        cur = response
        for _ in range(max_hops):
            if cur.status_code not in (301, 302, 303, 307, 308):
                # Sometimes the code lands on the final URL after allow_redirects
                qs = parse_qs(urlparse(cur.url).query)
                if qs.get("code"):
                    return qs["code"][0]
                break
            loc = cur.headers.get("Location")
            if not loc:
                break
            next_url = urljoin(cur.url if cur.url else self.cfg["origin"], loc)
            qs = parse_qs(urlparse(next_url).query)
            if qs.get("code"):
                got_state = (qs.get("state") or [None])[0]
                if got_state and got_state != expected_state:
                    raise RuntimeError(
                        f"OAuth state mismatch: expected {expected_state}, got {got_state}"
                    )
                # Do not GET loginCallback — code is single-use; exchange directly.
                return qs["code"][0]
            cur = self.session.get(next_url, timeout=30, allow_redirects=False)
        return None

    def _login_remotecontrol_form(self) -> None:
        """Legacy HTML form on portal_loginpath (pre-OpenID RemoteControl)."""
        url = self.cfg["login_url"]
        r = self.session.get(url, timeout=30)
        r.raise_for_status()
        if not (
            'id="Login"' in r.text
            or "id='Login'" in r.text
            or 'name="Login"' in r.text
        ):
            raise RuntimeError("Login form not found on portal_loginpath")

        token = None
        m = re.search(
            r'name="__RequestVerificationToken"[^>]*value="([^"]+)"',
            r.text,
        )
        if m:
            token = m.group(1)
        payload = {
            "Login": secrets.portal_user,
            "Password": secrets.portal_password,
        }
        if token:
            payload["__RequestVerificationToken"] = token
        post = self.session.post(
            r.url,
            data=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": self.cfg["origin"],
                "Referer": r.url,
            },
            timeout=30,
            allow_redirects=True,
        )
        post.raise_for_status()

    def _auth_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json;charset=UTF-8"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    # -- HTTP helpers ---------------------------------------------------------

    def _api_url(self, path: str) -> str:
        return f"{self.cfg['api_base']}/{path.lstrip('/')}"

    def post(self, path: str, payload: dict | None = None) -> Any:
        self.ensure_token()
        r = self.session.post(
            self._api_url(path),
            headers=self._auth_headers(),
            json=payload or {},
            timeout=30,
        )
        if r.status_code == 401:
            self.login()
            r = self.session.post(
                self._api_url(path),
                headers=self._auth_headers(),
                json=payload or {},
                timeout=30,
            )
        if r.status_code == 401:
            raise PermissionError(f"API 401 on {path} — re-login failed")
        r.raise_for_status()
        if not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            return r.text

    def get(self, path: str) -> Any:
        self.ensure_token()
        r = self.session.get(
            self._api_url(path),
            headers=self._auth_headers(),
            timeout=30,
        )
        if r.status_code == 401:
            self.login()
            r = self.session.get(
                self._api_url(path),
                headers=self._auth_headers(),
                timeout=30,
            )
        if r.status_code == 401:
            raise PermissionError(f"API 401 on {path}")
        r.raise_for_status()
        return r.json()

    # -- endpoints ------------------------------------------------------------

    def get_favorites(self, only_home: bool = False) -> list[dict]:
        iid = self.cfg["installation_id"]
        data = self.post(
            f"Favorite/GetFavorites/{iid}",
            {"WithDetails": True, "OnlyHomeScreen": only_home},
        )
        return (data or {}).get("ResponseData") or []

    def get_all_devices(self) -> list[dict]:
        iid = self.cfg["installation_id"]
        data = self.get(f"Device/GetAllDevices/{iid}")
        return (data or {}).get("ResponseData") or []

    def get_bundles(self, category: int = 0, device_id: str | None = None) -> list[dict]:
        """All datapoints for a device (cat 0=status/sensors, 1=settings)."""
        iid = self.cfg["installation_id"]
        data = self.post(
            f"Menu/GetBundlesByCategory/{iid}",
            {
                "DeviceId": device_id or self.cfg["device_id"],
                "Category": category,
            },
        )
        return (data or {}).get("ResponseData") or []

    def read_values(self, datapoints: list[dict]) -> list[dict]:
        """datapoints: {config_id, device_id, type?}"""
        iid = self.cfg["installation_id"]
        body = {
            "DatapointValues": [
                {
                    **({"$type": dp["type"]} if dp.get("type") else {}),
                    "DatapointConfigId": dp["config_id"],
                    "DeviceId": dp.get("device_id") or self.cfg["device_id"],
                }
                for dp in datapoints
            ]
        }
        data = self.post(f"Datapoint/ReadValues/{iid}", body)
        return (data or {}).get("ResponseData") or []

    def iter_bundle_datapoints(self, categories: tuple[int, ...] = (0, 1)):
        """Yield normalized datapoint dicts from GetBundlesByCategory."""
        for cat in categories:
            for bundle in self.get_bundles(cat):
                for dp in bundle.get("Datapoints") or []:
                    cfg = dp.get("Config") or dp.get("DatapointConfig") or {}
                    val = dp.get("DatapointValue") or {}
                    yield {
                        "config_id": cfg.get("DatapointConfigId")
                        or val.get("DatapointConfigId"),
                        "device_id": val.get("DeviceId") or self.cfg["device_id"],
                        "display_name": cfg.get("DisplayName"),
                        "well_known": cfg.get("WellKnownName"),
                        "unit": cfg.get("Unit"),
                        "value": val.get("Value"),
                        "possible_values": cfg.get("PossibleValues") or {},
                        "type": val.get("$type") or cfg.get("$type"),
                        "category": cat,
                    }

    # -- mapping to MQTT keys -------------------------------------------------

    def discover_rows(self) -> list[dict[str, Any]]:
        """Flat list from device bundles (not just sparse favorites)."""
        rows = []
        for row in self.iter_bundle_datapoints((0, 1)):
            row = dict(row)
            row["mqtt_guess"] = self._guess_mqtt_key(
                row.get("config_id"),
                row.get("display_name"),
                row.get("well_known"),
            )
            rows.append(row)
        return rows

    def _guess_mqtt_key(
        self,
        config_id: str | None,
        display: str | None,
        wellknown: str | None,
    ) -> str | None:
        id_map = _datapoint_map()
        if config_id and config_id.lower() in id_map:
            return id_map[config_id.lower()]
        if wellknown and wellknown in WELLKNOWN_TO_MQTT:
            return WELLKNOWN_TO_MQTT[wellknown]
        if wellknown and wellknown in WELLKNOWN_FALLBACK_TO_MQTT:
            return WELLKNOWN_FALLBACK_TO_MQTT[wellknown]
        if display and display in NAME_TO_MQTT:
            return NAME_TO_MQTT[display]
        return None

    def _coerce_mqtt_value(
        self,
        raw: Any,
        mqtt_key: str,
        *,
        possible_values: dict | None = None,
        well_known: str | None = None,
    ) -> Any:
        """Match scrape_heizkreis: first token, no unit; Heizleistung '-' -> 0."""
        if raw is None:
            return None

        # Enum / bool labels
        if mqtt_key == "WP-Zustand":
            label = None
            if possible_values is not None:
                label = possible_values.get(str(raw), possible_values.get(raw))
            if label is None and isinstance(raw, int):
                # fallback numeric map from known EE enum
                label = {
                    0: "Aus",
                    1: "Ein-Standby",
                    2: "Ein-HZW",
                    3: "Ein-BWW",
                    4: "Ein-Abt",
                    5: "Aus-EVU",
                    6: "Aus-Ala",
                    7: "Kühlen",
                    8: "Sperrzeit/Kontrollzeit",
                }.get(raw)
            if label:
                return WP_ZUSTAND_LABELS.get(label, label.split("-")[-1] if label else raw)
            return raw

        if mqtt_key == "Mischer":
            # Raw value is a step index (PossibleValueKey MS), not percent:
            # 0→100, 1→75, 2→50, 3→25, 4→0
            if possible_values:
                label = possible_values.get(str(raw), possible_values.get(raw))
                if label is not None:
                    return str(label)
            # Fallback if PossibleValues missing from payload
            step_map = {0: "100", 1: "75", 2: "50", 3: "25", 4: "0"}
            if isinstance(raw, (int, float)) and int(raw) in step_map:
                return step_map[int(raw)]
            return raw

        if mqtt_key == "Modus":
            # SummerModeHk1 True => Aus (matches overlay when circuit off)
            if well_known == "SummerModeHk1" or isinstance(raw, bool):
                return "Aus" if raw in (True, "True", "true", 1) else "Heizen"
            return raw

        if mqtt_key == "Ventil":
            # Umschaltventil: True=TWE, False=Puffer (winter overlay used "Puffer")
            if isinstance(raw, bool) or well_known == "HP_StatusUmschaltventilTWE":
                return "TWE" if raw in (True, "True", "true", 1) else "Puffer"
            return raw

        if mqtt_key == "WP Umwälz":
            if isinstance(raw, bool):
                return "Ein" if raw else "Aus"
            return raw

        if mqtt_key == "Heizkreis":
            text = str(raw)
            m = re.search(r"(\d+)", text)
            return m.group(1) if m else text.split(" ")[0]

        if mqtt_key == "Heizleistung":
            if raw in ("-", "", None):
                return 0
            if isinstance(raw, (int, float)) and float(raw) == 0:
                return 0

        if mqtt_key == "Zustand seit":
            # Keep a changing stamp for app.py stale detection (ISO ok).
            return str(raw).replace("T", " ").replace("Z", "")

        if isinstance(raw, float):
            text = f"{raw:.3f}".rstrip("0").rstrip(".")
            return text.replace(".", ",") if False else text  # app.py normalizes commas
        if isinstance(raw, bool):
            return "Ja" if raw else "Nein"
        # First token like scrape (e.g. "30,9 °C" -> "30,9")
        if isinstance(raw, str) and " " in raw:
            return raw.split(" ")[0]
        return raw

    def _read_extra_wellknown(self, names: tuple[str, ...]) -> dict[str, Any]:
        """Fetch datapoints that may be missing from bundles (e.g. LastChanged, COP)."""
        # Resolve IDs via GetConfigs using known JS wellknown UUIDs where needed
        known_ids = {
            "HeatpumpStateLastChanged": "965d09ef-88db-4d10-91cd-bbe8d713bf38",
            "MK1Name": None,  # often in bundles already
            "HP_Link_AktuellerPuffersollwert": "c8797976-59ee-45f3-856a-5aec3693736c",
            "HP_TotalCOP": "34760a09-8f79-424f-a1b0-5f1a9339d864",
        }
        want = [n for n in names if n in known_ids and known_ids[n]]
        if not want:
            return {}
        iid = self.cfg["installation_id"]
        ids = [known_ids[n] for n in want]
        cfg = self.post(
            f"Datapoint/GetConfigs/{iid}",
            {
                "DeviceType": 2,
                "DeviceVersion": "6.0",
                "DatapointConfigIds": ids,
                "IgnoreNotExisting": True,
            },
        )
        cfgs = (cfg or {}).get("ResponseData") or []
        if not cfgs:
            return {}
        dps = []
        by_id = {}
        for c in cfgs:
            cid = c["DatapointConfigId"]
            by_id[cid.lower()] = c
            dps.append(
                {
                    "config_id": cid,
                    "device_id": self.cfg["device_id"],
                    "type": (c.get("$type") or "").replace(
                        "DatapointConfig`1", "DatapointValue`1"
                    ),
                }
            )
        out: dict[str, Any] = {}
        for item in self.read_values(dps):
            c = by_id.get((item.get("DatapointConfigId") or "").lower(), {})
            wk = c.get("WellKnownName")
            if wk:
                out[wk] = {
                    "value": item.get("Value"),
                    "possible_values": c.get("PossibleValues") or {},
                    "display_name": c.get("DisplayName"),
                    "well_known": wk,
                }
        return out

    @staticmethod
    def _as_float(value: Any) -> float | None:
        if value is None or value == "" or value is False:
            return None
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return None

    def _finalize_cop(self, data: dict[str, Any], raw_cop: dict[str, Any]) -> None:
        """COP = Aktueller COP (HP_TotalCOP) only; 0 when idle / null. Never mix sensors."""
        instant = self._as_float(raw_cop.get("HP_TotalCOP"))
        data["COP"] = self._coerce_mqtt_value(0.0 if instant is None else instant, "COP")

    def fetch_heizkreis(self) -> dict[str, Any]:
        """Return Heizkreis keys + separate KPI entities (COP/SCOP/S0 never mixed)."""
        data: dict[str, Any] = {}
        meta: dict[str, dict] = {}
        raw_cop: dict[str, Any] = {}

        for row in self.iter_bundle_datapoints((0, 1)):
            wk = row.get("well_known")
            if wk == "HP_TotalCOP":
                raw_cop[wk] = row.get("value")

            key = self._guess_mqtt_key(
                row.get("config_id"),
                row.get("display_name"),
                wk,
            )
            if not key or key not in MQTT_HEIZKREIS_KEYS:
                continue
            # Prefer category-0 sensor values; don't overwrite with settings unless empty
            if key in data and row.get("category") == 1:
                continue
            # Never let a fallback source overwrite an already-filled key
            # (e.g. Aktuelle Ventilöffnung must win over Regelsignal …).
            if key in data and wk in WELLKNOWN_FALLBACK_TO_MQTT:
                continue
            if key in data and meta.get(key, {}).get("well_known") in WELLKNOWN_TO_MQTT:
                continue
            # Skip writing COP from bundle here — finalized only from HP_TotalCOP
            if key == "COP":
                raw_cop.setdefault("HP_TotalCOP", row.get("value"))
                continue
            data[key] = self._coerce_mqtt_value(
                row.get("value"),
                key,
                possible_values=row.get("possible_values"),
                well_known=wk,
            )
            meta[key] = row

        # Fill gaps (Zustand seit, Puffer Soll, Aktueller COP, …)
        extras = self._read_extra_wellknown(EXTRA_READ_WELLKNOWN)
        for wk, info in extras.items():
            if wk == "HP_TotalCOP":
                raw_cop["HP_TotalCOP"] = info.get("value")
                continue
            key = WELLKNOWN_TO_MQTT.get(wk) or WELLKNOWN_FALLBACK_TO_MQTT.get(wk)
            if key and key not in data and info.get("value") is not None:
                data[key] = self._coerce_mqtt_value(
                    info.get("value"),
                    key,
                    possible_values=info.get("possible_values"),
                    well_known=wk,
                )

        self._finalize_cop(data, raw_cop)

        # Match Selenium overlay: Vorlauf Soll/Ist omitted when Heizkreis is off.
        if data.get("Modus") == "Aus":
            data.pop("Vorlauf Soll", None)
            data.pop("Vorlauf Ist", None)

        missing = [k for k in MQTT_HEIZKREIS_KEYS if k not in data]
        if not any(k in data for k in ("Aussentemp.", "Heizleistung", "WP-Zustand")):
            raise ConnectionError(
                "Portal API lieferte keine Heizkreis-Kernwerte — "
                f"Mapping prüfen (missing={missing[:8]}…)"
            )

        return data


def mqtt_topic_for_key(key: str) -> str:
    """Keys starting with ``swisstherm_`` are flat topics; others ``swisstherm/<key>``."""
    return key if str(key).startswith("swisstherm_") else f"swisstherm/{key}"


def publish_heizkreis_mqtt(mqtt_client, data: dict[str, Any]) -> None:
    """Same publish pattern as app.py (topics + comma->dot)."""
    now = datetime.datetime.now()
    payload = dict(data)
    payload["Timestamp"] = now
    payload["Date"] = now.strftime("%d.%m.%Y")
    payload["Time"] = now.strftime("%H:%M:%S")
    for key, value in payload.items():
        mqtt_client.publish(
            mqtt_topic_for_key(key),
            payload=str(value).replace(",", "."),
        )


def _print_discover(rows: list[dict]) -> None:
    mapped = [r for r in rows if r.get("mqtt_guess")]
    print(f"Bundles datapoints: {len(rows)}, mapped to MQTT: {len(mapped)}")
    print(f"{'MQTT guess':18} {'Display':36} {'WellKnown':36} Value")
    print("-" * 110)
    for row in sorted(mapped, key=lambda r: MQTT_HEIZKREIS_KEYS.index(r["mqtt_guess"]) if r["mqtt_guess"] in MQTT_HEIZKREIS_KEYS else 99):
        print(
            f"{(row['mqtt_guess'] or '-'):18.18} "
            f"{(row['display_name'] or '-'):36.36} "
            f"{(row['well_known'] or '-'):36.36} "
            f"{row['value']!r}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "command",
        choices=("discover", "once", "devices"),
        help="discover=dump bundles mapping; once=Heizkreis dict; devices=list devices",
    )
    parser.add_argument(
        "--mqtt",
        action="store_true",
        help="Publish once to swisstherm/* (requires MQTT secrets)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON",
    )
    args = parser.parse_args(argv)

    cfg = derive_portal_config()
    print(
        f"API {cfg['api_base']}  installation={cfg['installation_id']}  "
        f"device={cfg['device_id']}",
        file=sys.stderr,
    )

    client = PortalApiClient(cfg)
    print("Login…", file=sys.stderr)
    client.login()

    if args.command == "devices":
        devices = client.get_all_devices()
        print(json.dumps(devices, indent=2, ensure_ascii=False, default=str))
        return 0

    if args.command == "discover":
        rows = client.discover_rows()
        if args.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
        else:
            _print_discover(rows)
        return 0

    # once
    data = client.fetch_heizkreis()
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    else:
        for k in MQTT_HEIZKREIS_KEYS:
            if k in data:
                human = MQTT_HUMAN_NAMES.get(k, k)
                print(f"{human:28} {k:28} {data[k]}")
        missing = [k for k in MQTT_HEIZKREIS_KEYS if k not in data]
        if data.get("Modus") == "Aus":
            missing = [k for k in missing if k not in ("Vorlauf Soll", "Vorlauf Ist")]
        if missing:
            print(f"\nMissing keys ({len(missing)}): {', '.join(missing)}")

    if args.mqtt:
        import paho.mqtt.client as mqtt

        mq = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        mq.username_pw_set(secrets.mqtt_user, password=secrets.mqtt_pwd)
        mq.connect(secrets.mqtt_host, secrets.mqtt_port, 60)
        mq.loop_start()
        publish_heizkreis_mqtt(mq, data)
        mq.publish("swisstherm/status", payload="Portal-API once OK")
        mq.loop_stop()
        mq.disconnect()
        print("Published to swisstherm/*", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
