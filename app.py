# Gemäss https://selenium-python.readthedocs.io - leicht ergänzt
# Funktionierende Abfrage - ohne executable_path-Warnung und headless gem. https://youtu.be/LN1a0JoKlX8

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import datetime
import sys

import functions
import secrets
import paho.mqtt.client as mqtt

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

abrufversuche = 0
for abrufversuche in range(5):  # Anzahl Versuche im Fehlerfall

    time.sleep(abrufversuche * 30)
    abrufversuche += 1

    try:
        driver = webdriver.Chrome(options=options)
        functions.login(driver)  # Anmelden mit separater Funktion

        # The callback for when the client receives a CONNACK response from the server.
        def on_connect(client, userdata, flags, rc):
            print("MQQT connected with result code " + str(rc))

            # Subscribing in on_connect() means that if we lose the connection and
            # reconnect then subscriptions will be renewed.
            client.subscribe("swisstherm/control/#")

        control = {
            'onoff': '',
            'delay': 30  # Sekunden (Intervall Datenabruf)
        }

        # The callback for when a PUBLISH message is received from the server.
        def on_message(client, userdata, msg):
            received = str(msg.payload.decode("utf-8"))
            if msg.topic == "swisstherm/control/onoff":
                 control['onoff'] = received
            if msg.topic == "swisstherm/control/delay":
                 control['delay'] = received
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

        print('Laden...')

        element = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.main'))
        )

        # if abrufversuche > 2:
        #    raise TimeoutError('Test')  # zum Testen des Fehlerfalls

        #  Betriebsdaten Heizkreisübersicht
        driver.get(secrets.datapath)

        element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.overlay'))
        )
        time.sleep(5)

        data = {}
        refresh_check = {
            'count': 0,
            'value': ""
        }

        x = 0
        while control['onoff'] != "stop":  # Endlosschleife mit "while True" oder begrenzt mit "while x in range(n)>"
            if x > 0:
                time.sleep(int(control['delay']))
            else:
                client.publish('swisstherm/status', payload='Abfrage gestartet')
            x += 1

            values = driver.find_elements(By.CSS_SELECTOR, 'div.row.g-g > div > div')

            refresh_check['value'] = data.get("Zustand seit")  # Speichern des letzten Werts für die Aktualisierungs-Prüfung.
            refresh_check['count'] = 0

            linke_zeilen = values[0].text.split('\n')
            heizleistung = linke_zeilen[0].split(': ')
            hl = heizleistung[1].split(' ')[0]
            if hl == '-':
                data[heizleistung[0]] = 0
            else:
                data[heizleistung[0]] = hl
            cop = linke_zeilen[1].split(': ')
            data[cop[0]] = cop[1]

            # raise IndexError('Test')  # Zum Testen des Fehlerfalls

            data["Zustand seit"] = values[1].text.strip()

            # Prüfung, ob Daten auf Webseite noch aktualisiert werden. Sonst Neustart.
            if data["Zustand seit"] == refresh_check['value']:
                refresh_check['count'] += 1
                if refresh_check['count'] * control['delay'] >= 120:
                    client.publish('swisstherm/status', payload='Daten nicht aktualisiert - Neustart...')
                    raise IndexError('Daten nicht aktualisiert - Neustart...')

            rechte_zeilen = values[2].text.split('\n')
            aussentemp = rechte_zeilen[0].split(': ')
            data[aussentemp[0].replace('Außentemperatur', 'Aussentemp.')] = aussentemp[1].split(' ')[0]
            wpzustand = rechte_zeilen[1].split(': ')
            data[wpzustand[0].replace('Wärmepumpenzustand', 'WP-Zustand')] = wpzustand[1]

            values = driver.find_elements(By.CSS_SELECTOR, 'div.overlay span')
            keys = ["Heizkreis", "Vorlauf", "Rücklauf", "Mischer", "Modus", "Ventil",
                    "WP Rückl.", "WP Vorl.", "WP Umwälz", "WP UW Öffn", "WP UW Hyst", "WP UW Flow",
                    "TWE Max", "TWE Ist", "TWE Hyst", "Puffer Max", "Puffer Ist", "Puffer Hyst"]
            i = 0
            for key in keys:
                data[key] = values[i].text.split(' ')[0]
                i += 1

            data["Timestamp"] = datetime.datetime.now()
            data["Date"] = datetime.datetime.now().strftime("%d.%m.%Y")
            data["Time"] = datetime.datetime.now().strftime("%H:%M:%S")

            # functions.printdata(data)
            # functions.writefile(data)

            for key in data:
                client.publish('swisstherm/'+key, payload=str(data[key]).replace(',','.'))
                # print(f'{key:16}{data[key]}')

            print(f'Loop {x} OK, {len(data)} items')
            abrufversuche = 0  # zurücksetzen, wenn alles ordentlich läuft

        break  # Damit nach ordentlichem Verlassen der inneren Schleife das Programm beendet wird

    except:
        print(f'Fehler beim Abruf der Swisstherm-Heizkreisdaten (Versuch {abrufversuche}): ', sys.exc_info())
        client.publish('swisstherm/status', payload=f'Fehler beim Abruf der Swisstherm-Heizkreisdaten (Versuch {abrufversuche}): {sys.exc_info()}')

    driver.close()
    client.loop_stop()

print('Abruf Swisstherm-Heizkreisdaten wurde beendet.')
