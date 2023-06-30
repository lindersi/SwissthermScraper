from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
import secrets
import time


def login(driver):
    driver.get(secrets.portal_loginpath)
    print('Anmelden...')
    time.sleep(2)
    assert "Login" in driver.title
    elem = driver.find_element(By.ID, "Login")
    elem.clear()
    elem.send_keys(secrets.portal_user)
    elem = driver.find_element(By.ID, "Password")
    elem.clear()
    elem.send_keys(secrets.portal_password)
    elem.send_keys(Keys.RETURN)


def printdata(data):
    for item in data:
        print(f'{item:16}{data[item]}')
    print('-' * 42)


def writefile(data):
    filename = 'heizkreis_history.csv'
    with open(filename, mode='a', encoding='utf-8') as f:
        if f.tell() == 0:
            for key in data:
                f.write(key + '\t')
            f.write('\n')
        for key in data:
            f.write(str(data[key]) + '\t')
        f.write('\n')
        f.close()
    print(f'Data written to {filename}\n')

