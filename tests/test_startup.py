import pytest
from playwright.sync_api import Page


@pytest.mark.playwright
def test_login_page_is_visible_playwright(page: Page):
    page.goto('http://localhost')
    page.get_by_role('textbox', name='Your email').fill('test@example.com')
    page.get_by_role("button", name="Continue").click()
