# Derivat von app.py zum sporadischen Abruf der Energiedaten und
# senden an Google Spreadsheet (statt von Hand abschreiben)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import datetime
import sys

import functions
import secrets

def energiezaehler(options, client):

    client.publish('swisstherm/status/zaehler', payload='Abruf Swisstherm-Zählerstände läuft...')
    print('Abruf Swisstherm-Zählerstände läuft...')

    try:
        data = {}
        for zaehlerwahl in secrets.portal_datapath_energy:

            driver = webdriver.Chrome(options=options)

            functions.login(driver)  # Anmelden mit separater Funktion
            print(f'Laden Zähler {zaehlerwahl}...')

            element = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div.main'))
            )

            #  Energiezähler (Geräte > xcenter x40 > DYNAMIC > Status > Leistung und Effizienz)
            driver.get(secrets.portal_datapath_energy[zaehlerwahl])

            element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div.row'))
            )
            time.sleep(2)

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

        for key in data:
            client.publish('swisstherm/zaehler/'+key, payload=str(data[key]).replace(',','.'))
            print(f'{key:16}{data[key]}')
        client.publish('swisstherm/status', payload=f'Zähler abgerufen ({len(data)} Werte).')

    except:
        print(f'Fehler beim Abruf der Swisstherm-Energiezähler: ', sys.exc_info())
        client.publish('swisstherm/status', payload=f'Fehler beim Abruf der Swisstherm-Energiezähler: {sys.exc_info()}')

    print('Abruf Swisstherm-Energiezähler wurde beendet.')
    client.publish('swisstherm/status', payload='Abruf Swisstherm-Energiezähler wurde beendet.')
