# Derivat von app.py zum sporadischen Abruf der Energiedaten und
# senden an Google Spreadsheet (statt von Hand abschreiben)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
import time
import datetime
import sys
import json

import functions
# import gsheet
import secrets


def energiezaehler(options, client):

    client.publish('swisstherm/status', payload='Abruf Swisstherm-Zählerstände läuft...')
    print('Abruf Swisstherm-Zählerstände läuft...')

    data = {}

    try:

        driver = webdriver.Chrome(options=options)

        functions.login(driver)  # Anmelden mit separater Funktion

        WebDriverWait(driver, 30).until(
            ec.presence_of_element_located((By.CSS_SELECTOR, 'div.main'))
        )
        startfenster = driver.current_window_handle

        for zaehlerwahl in secrets.portal_datapath_energy:

            driver.switch_to.new_window(zaehlerwahl)
            #  Energiezähler (Geräte > xcenter x40 > DYNAMIC > Status > Leistung und Effizienz)
            driver.get(secrets.portal_datapath_energy[zaehlerwahl])

            WebDriverWait(driver, 30).until(
                ec.presence_of_element_located((By.CSS_SELECTOR, 'div.row'))
            )
            time.sleep(5)

            values = driver.find_elements(By.CSS_SELECTOR, 'div.row.g-g > div > div')

            if "Wärmemenge" in values[6].text.split(" ")[0]:
                data[values[6].text] = values[7].text.split(" ")[0]  # Wärmemenge Gesamt / Hz / TWE
                data[values[10].text] = values[11].text.split(" ")[0]  # Leistungsaufnahme Gesamt / Hz /  TWE
                data[values[14].text] = values[15].text  # Gemittelter COP Gesamt / Hz / TWE
                data[values[18].text] = values[19].text.split(" ")[0]  # Betriebsminuten Gesamt / Hz / TWE
            elif "Betriebsstunden" in values[6].text.split(" ")[0]:
                data[values[22].text] = values[23].text.split(" ")[0]  # Betriebsstunden ext. WEZ 1
                data[values[26].text] = values[27].text.split(" ")[0]  # Betriebsstunden ext. WEZ 2
            else:
                raise ValueError

            driver.close()
            driver.switch_to.window(startfenster)

        data["Date"] = datetime.datetime.now().strftime("%d.%m.%Y")
        data["Time"] = datetime.datetime.now().strftime("%H:%M:%S")

        # for key in data:
            # client.publish('swisstherm/zaehler/'+key, payload=str(data[key]).replace(',', '.'))
            # print(f'{key:16}{data[key]}')
        client.publish('swisstherm/zaehler/json', payload=json.dumps(data))
        client.publish('swisstherm/status', payload=f'Zähler abgerufen ({len(data)} Werte).')

        driver.quit()

    except:
        print(f'Fehler beim Abruf der Swisstherm-Energiezähler: ', sys.exc_info())
        client.publish('swisstherm/status',
                       payload=f'Notify: Fehler beim Abruf der Swisstherm-Energiezähler: {sys.exc_info()}')
        driver.quit()

    print('Swisstherm-Energiezähler erfolgreich abgerufen.')
    client.publish('swisstherm/status', payload='Notify: Swisstherm-Energiezähler erfolgreich abgerufen.')

    # gsheet.main(data, client)


def write_data(data):
    file = open("energy-data.txt", "w")
    file.write(json.dumps(data))
    file.close()
