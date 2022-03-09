# Derivat von app.py zum sporadischen Abruf der Energiedaten und
# senden an Google Spreadsheet (statt von Hand abschreiben)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import datetime
import sys
import socket

import functions
import secrets
import paho.mqtt.client as mqtt


# ------------------------------------------------------
# MQTT

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print("MQQT connected with result code " + str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("swisstherm/control/#")


# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    received = str(msg.payload.decode("utf-8"))
    if msg.topic == "swisstherm/control/onoff":
        control['onoff'] = received
    if msg.topic == "swisstherm/control/delay":
        control['delay'] = int(received)
    if msg.topic == "swisstherm/control/waittime":
        control['waittime'] = int(received)
    if msg.topic == "swisstherm/control/retries":
        control['retries'] = int(received)
    print(msg.topic + " " + received)


client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.username_pw_set(secrets.mqtt_user, password=secrets.mqtt_pwd)

client.connect(secrets.mqtt_host, secrets.mqtt_port, 60)

# Blocking call that processes network traffic, dispatches callbacks and
# handles reconnecting.
# Other loop*() functions are available that give a threaded interface and a
# manual interface.
client.loop_start()

control = {
    'onoff': '',
    'delay': 30,  # Sekunden (Intervall Datenabruf)
    'waittime': 5,  # Minuten zwischen Abrufversuchen, resp. Neuverbindungen mit dem Swisstherm-Portal
    'retries' : 0  # Anzahl Neuverbindungs-Versuche vor Programmabbruch
}

host = socket.gethostname()

client.publish('swisstherm/status', payload=f'Swisstherm-Scraper auf {host} zum einmaligen Energie-Abruf gestartet.')

user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) " \
             "Chrome/96.0.4664.45 Safari/537.36"

options = webdriver.ChromeOptions()
options.headless = True
options.add_argument(f'user-agent={user_agent}')
options.add_argument("--window-size=1024,768")
options.add_argument('--ignore-certificate-errors')
options.add_argument('--allow-running-insecure-content')
options.add_argument("--disable-extensions")
options.add_argument("--proxy-server='direct://'")
options.add_argument("--proxy-bypass-list=*")
options.add_argument("--start-maximized")
options.add_argument('--disable-gpu')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--no-sandbox')

try:

    data = {}

    for zaehlerwahl in secrets.portal_datapath_energy:

        driver = webdriver.Chrome(options=options)
        functions.login(driver)  # Anmelden mit separater Funktion

        print(f'Laden Zähler {zaehlerwahl}...')
        client.publish('swisstherm/status', payload=f'Anmeldung erfolgreich. Seite Zähler {zaehlerwahl} laden...')

        element = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.main'))
        )

        #  Energiezähler (Geräte > xcenter x40 > DYNAMIC > Status > Leistung und Effizienz)
        driver.get(secrets.portal_datapath_energy[zaehlerwahl])

        element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.row'))
        )
        time.sleep(2)

        client.publish('swisstherm/status', payload='Abfrage gestartet')

        values = driver.find_elements(By.CSS_SELECTOR, 'div.row.g-g > div > div')

        assert values[6].text.split(" ")[0] == "Wärmemenge", "Werte nicht gefunden."
        data[values[6].text] = values[7].text.split(" ")[0]  # Wärmemenge Hz / TWE
        data[values[10].text] = values[11].text.split(" ")[0]  # Leistungsaufnahme Hz /  TWE
        data[values[14].text] = values[15].text  # Gemittelter COP Hz / TWE
        data[values[18].text] = values[19].text.split(" ")[0]  # Betriebsminuten Hz / TWE

        driver.quit()

    data["Timestamp"] = datetime.datetime.now()
    data["Date"] = datetime.datetime.now().strftime("%d.%m.%Y")
    data["Time"] = datetime.datetime.now().strftime("%H:%M:%S")

    # functions.printdata(data)
    # functions.writefile(data)

    for key in data:
        client.publish('swisstherm/zaehler/'+key, payload=str(data[key]).replace(',','.'))
        print(f'{key:16}{data[key]}')
    client.publish('swisstherm/status', payload=f'Zähler abgerufen. {len(data)} Werte von {host} gesendet.')

except:
    print(f'Fehler beim Abruf der Swisstherm-Energiezähler: ', sys.exc_info())
    client.publish('swisstherm/status', payload=f'Fehler beim Abruf der Swisstherm-Energiezähler: {sys.exc_info()}')

print('Abruf Swisstherm-Energiezähler wurde beendet.')
client.publish('swisstherm/status', payload='Abruf Swisstherm-Energiezähler wurde beendet.')
client.loop_stop()
