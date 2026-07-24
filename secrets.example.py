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
