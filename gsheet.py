from __future__ import print_function

import os.path
import json
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# The ID and range of the spreadsheet.
SPREADSHEET_ID = '1Pny7iRRp4aL3n-oTF155LaL44Wf4mf7ZcZhidHeyqik'
RANGE_NAME = 'Energieverbrauch!A:G'


def main(data, client):
    try:
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.json', 'w') as token:
                token.write(creds.to_json())

        service = build('sheets', 'v4', credentials=creds)

        # Call the Sheets API
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID,
                                    range=RANGE_NAME).execute()
        values = result.get('values', [])

        x = 0
        for x in range(20):
            if "Datum" in values[x]:
                break
        print(f'Spreadsheet Kopfzeile: Nr. {x + 1}')
        new_row = len(values) + 1
        print(f'Spreadsheet Nächste Zeile: {new_row}')

        if not data:
            data = get_data()

        # Schreiben gem. https://developers.google.com/sheets/api/guides/values#python_2
        writerange = f'A{new_row}:G'
        writevalues = [
            [
                data['Date'], data['Time'], data['Gesamt-Leistungsaufnahme Hz/TWE'], data['Leistungsaufnahme Hz'],
                data['Leistungsaufnahme TWE'], data['Betriebsstunden externer WEZ 1'],
                data['Betriebsstunden externer WEZ 2']
            ]
        ]
        body = {
            'values': writevalues
        }
        result = service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID, range=writerange, valueInputOption='USER_ENTERED', body=body).execute()
        print('{0} cells appended.'.format(result.get('updatedCells')))
    except HttpError as err:
        print(err)

    except:
        print(f'Fehler beim Anmelden/Schreiben in Google Sheets: ', sys.exc_info())
        client.publish('swisstherm/status',
                       payload=f'Notify: Fehler beim Anmelden/Schreiben in Google Sheets: {sys.exc_info()}')


def get_data():
    file = open('energy-data.txt', 'r', encoding='utf-8')
    data = json.loads(file.read())
    for item in data:
        print(f'{item:24}{data[item]}')
    return data
