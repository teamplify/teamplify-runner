import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By


@pytest.fixture
def driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--nogpu")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(2)
    return driver


@pytest.mark.selenium
def test_login_page_is_visible(driver):
    driver.get('http://localhost')
    email_field = driver.find_element(By.NAME, 'email')
    email_field.send_keys('test@example.com')
    button_element = driver.find_element(By.XPATH, "//button[contains(.,'Continue')]")
    button_element.click()
