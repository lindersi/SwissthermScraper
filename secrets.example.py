# Copy to secrets.py and fill in real values. secrets.py is gitignored.

portal_loginpath = "https://portal.example.ch/XCenterUI/RemoteControl/de/de/YOUR-UUID"
portal_user = "user@example.com"
portal_password = "changeme"
portal_datapath = {
    "Heizkreis": portal_loginpath + "/device/DEVICE-UUID/OverviewHeatingCircuit/00000000-0000-0000-0000-000000000000",
    "Hauptbild": portal_loginpath + "/main",
}
portal_datapath_energy = {
    "Gesamt": portal_loginpath + "/device/DEVICE-UUID/COUNTER-UUID-1",
    "Heizung": portal_loginpath + "/device/DEVICE-UUID/COUNTER-UUID-2",
    "Trinkwasser": portal_loginpath + "/device/DEVICE-UUID/COUNTER-UUID-3",
    "Stunden": portal_loginpath + "/device/DEVICE-UUID/COUNTER-UUID-4",
}
mqtt_user = "mqttuser"
mqtt_pwd = "mqttpassword"
mqtt_host = "homeassistant"
mqtt_port = 1883

# Optional — portal_api_client.py overrides (Heizkreis + energy via JSON API).
# Defaults are derived from portal_loginpath / Heizkreis URL when omitted.
# Energy counters use the menu-entry UUID at the end of each portal_datapath_energy URL.
# portal_api_base = "https://portal.example.ch/xcenterpro/api"
# portal_installation_id = "YOUR-UUID"
# portal_device_id = "DEVICE-UUID"
# portal_openid_client_id = "XCenterUI"
# portal_openid_redirect_uri = "https://portal.example.ch/xcenterui/xcenter/auth/loginCallback"
# portal_openid_scopes = "openid email profile offline_access kermi.xcenter kermi.webcrm"
# portal_datapoint_map = {
#     # DatapointConfigId -> MQTT key (same names as scrape.py / swisstherm/<key>)
#     # "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee": "Aussentemp.",
# }
