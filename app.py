# Gemäss https://selenium-python.readthedocs.io - leicht ergänzt
# Funktionierende Abfrage - ohne executable_path-Warnung und headless gem. https://youtu.be/LN1a0JoKlX8
# Nach wiederholten Hängern (Fehler mit Selenium/Driver) umgebaut
# (Selenium komplett in Loop, MQTT ausserhalb mit mehr Statusmeldungen).

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
import time
import datetime
import sys
import socket

import functions
import energy
import secrets
import paho.mqtt.client as mqtt


# ------------------------------------------------------
# MQTT

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print("MQTT connected with result code " + str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("swisstherm/control/#")


# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    received = str(msg.payload.decode("utf-8"))
    print(msg.topic + " " + received)
    if msg.topic == "swisstherm/control/zaehler" and received == "get":
        client.publish('Abruf Energiezähler ausgelöst')
        energy.energiezaehler(options, client)
    if msg.topic == "swisstherm/control/onoff":
        control['onoff'] = received
    if msg.topic == "swisstherm/control/delay":
        control['delay'] = int(received)
    if msg.topic == "swisstherm/control/waittime":
        control['waittime'] = int(received)
    if msg.topic == "swisstherm/control/retries":
        control['retries'] = int(received)


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
    'waittime': 15,  # Minuten zwischen Abrufversuchen, resp. Neuverbindungen mit dem Swisstherm-Portal
    'retries': 50  # Anzahl Neuverbindungs-Versuche vor Programmabbruch
}

host = socket.gethostname()

client.publish('swisstherm/status',
               payload=f'Swisstherm-Scraper gestartet auf {host}, Abrufintervall (delay): {control["delay"]}s')


# ------------------------------------------------------
# Selenium-Abruf mit Wiederholung (Loop) im Fehlerfall
abrufversuche = 0

for abrufversuche in range(int(control['retries'])):  # Anzahl Versuche im Fehlerfall

    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) " \
                 "Chrome/96.0.4664.45 Safari/537.36"

    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--headless')
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

    if abrufversuche > 0:
        if abrufversuche == 1:
            wartezeit = 0.2
        elif abrufversuche < 4:
            wartezeit = 3
        else:
            wartezeit = int(control['waittime'])
        client.publish('swisstherm/status',
                       payload=f'Abrufversuch {abrufversuche}: Warte {wartezeit} min ...')
        time.sleep(wartezeit * 60)

    abrufversuche += 1

    driver = webdriver.Chrome(options=options)
    try:
        functions.login(driver)  # Anmelden mit separater Funktion

        print('Laden...')
        client.publish('swisstherm/status', payload=f'Anmeldung erfolgreich. Seite laden...')

        element = WebDriverWait(driver, 20).until(
            ec.presence_of_element_located((By.CSS_SELECTOR, 'div.main'))
        )

        #  Betriebsdaten Heizkreisübersicht
        driver.get(secrets.portal_datapath['Heizkreis'])

        WebDriverWait(driver, 10).until(
            ec.presence_of_element_located((By.CSS_SELECTOR, 'div.overlay'))
        )
        time.sleep(5)

        data = {}
        refresh_check = {
            'count': 0,
            'value': ""
        }

        x = 0
        while control['onoff'] != "stop":  # Endlosschleife mit "while True" oder begrenzt mit "while x in range(n)>"
            if control['onoff'] == "restart":
                control['onoff'] = ""
                raise InterruptedError('Neustart angefordert...')

            if x > 0:
                y = (4 if data['Modus'] == "Aus" else 1)  # Längeres Abrufintervall, wenn Heizkreis Aus
                time.sleep(int(control['delay']) * y)
            else:
                client.publish('swisstherm/status', payload='Abfrage gestartet')
            x += 1

            values = driver.find_elements(By.CSS_SELECTOR, 'div.row.g-g > div > div')

            refresh_check['value'] = data.get("Zustand seit")
            # Speichern des letzten Werts für die Aktualisierungs-Prüfung.

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
                if refresh_check['count'] * int(control['delay']) >= 120:
                    client.publish('swisstherm/status', payload='Notify: Daten nicht aktualisiert - Neustart...')
                    raise ConnectionError('Daten nicht aktualisiert - Neustart...')
            else:
                refresh_check['count'] = 0

            rechte_zeilen = values[2].text.split('\n')
            aussentemp = rechte_zeilen[0].split(': ')
            data[aussentemp[0].replace('Außentemperatur', 'Aussentemp.')] = aussentemp[1].split(' ')[0]
            wpzustand = rechte_zeilen[1].split(': ')
            data[wpzustand[0].replace('Wärmepumpenzustand', 'WP-Zustand')] = wpzustand[1]

            values = driver.find_elements(By.CSS_SELECTOR, 'div.overlay span')
            keys = ["Heizkreis", "Vorlauf Soll", "Vorlauf Ist", "Mischer", "Modus", "Ventil",
                    "WP Rückl.", "WP Vorl.", "WP Umwälz", "WP UW Öffn", "WP UW Hyst", "WP UW Flow",
                    "TWE Soll", "TWE Ist", "TWE Hyst", "Puffer Soll", "Puffer Ist", "Puffer Hyst"]

            if values[2].text.split(' ')[0] == "Aus":  # (Heizkreis-)Modus = "Aus"
                del keys[1:3]  # Einträge "Vorlauf Soll/Ist" entfernen (fehlen in dem Fall in der Heizkreisübersicht)
            elif values[4].text.split(' ')[0] != "Heizen":  # Gegen Fehler beim Zurückwechseln in Heizbetrieb
                client.publish('swisstherm/status', payload='Notify: Datenzuweisung fehlerhaft - Neustart...')
                raise ConnectionError('Datenzuweisung fehlerhaft - Neustart...')
            i = 0
            for key in keys:
                data[key] = values[i].text.split(' ')[0]
                print(f'{key:16}{data[key]}')
                i += 1

            data["Timestamp"] = datetime.datetime.now()
            data["Date"] = datetime.datetime.now().strftime("%d.%m.%Y")
            data["Time"] = datetime.datetime.now().strftime("%H:%M:%S")

            # functions.printdata(data)
            # functions.writefile(data)

            for key in data:
                client.publish('swisstherm/'+key, payload=str(data[key]).replace(',', '.'))
                # print(f'{key:16}{data[key]}')
            client.publish('swisstherm/status',
                           payload=f'Loop {x}, {len(data)} items sent from {host}, '
                                   f'delay={control["delay"]}s, refresh_check={refresh_check["count"]}')

            print(f'Loop {x} OK, {len(data)} items')
            abrufversuche = 0  # zurücksetzen, wenn alles ordentlich läuft

        break  # Damit nach ordentlichem Verlassen der inneren Schleife das Programm beendet wird

    except KeyboardInterrupt:
        client.publish('swisstherm/status', payload=f'Abruf der Swisstherm-Heizkreisdaten manuell abgebrochen')
        sys.exit(0)

    except:
        print(f'Fehler beim Abruf der Swisstherm-Heizkreisdaten (Versuch {abrufversuche}): ', sys.exc_info())
        client.publish('swisstherm/status',
                       payload=f'Fehler beim Abruf der Swisstherm-Heizkreisdaten '
                               f'(Versuch {abrufversuche}): {sys.exc_info()}')

    try:
        driver.close()
    except:
        print(f'Fehler: Chromium konnte nicht beendet werden. Weiter...')
        client.publish('swisstherm/status', payload=f'Fehler: Chromium konnte nicht beendet werden. Weiter...')

print('Abruf Swisstherm-Heizkreisdaten wurde beendet.')
client.publish('swisstherm/status', payload=f'Notify: Abruf Swisstherm-Heizkreisdaten von {host} wurde beendet.')
# Meldungen mit Stichwort "Notify: " werden von Home Assistant weiter geleitet (z.B. Pushnachricht mit notify.simon)!
client.loop_stop()
