from pathlib import Path
from playwright.sync_api import sync_playwright

out = Path(__file__).resolve().parent
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe', headless=True)
    page = browser.new_page(viewport={"width": 1366, "height": 768}, device_scale_factor=1)
    page.goto('https://datathon.com.kz/ru', wait_until='networkidle', timeout=45000)
    continue_button = page.get_by_text('ПРОДОЛЖИТЬ БЕЗ ЗВУКА', exact=False)
    if continue_button.count():
        continue_button.first.click()
        page.wait_for_timeout(1000)
    page.screenshot(path=str(out / 'reference-loaded.png'))
    page.reload(wait_until='domcontentloaded')
    page.wait_for_timeout(1800)
    continue_button = page.get_by_text('ПРОДОЛЖИТЬ БЕЗ ЗВУКА', exact=False)
    if continue_button.count():
        continue_button.first.click()
    page.screenshot(path=str(out / 'reference-intro-0.png'))
    page.wait_for_timeout(450)
    page.screenshot(path=str(out / 'reference-intro-450.png'))
    page.wait_for_timeout(1100)
    page.screenshot(path=str(out / 'reference-intro-1550.png'))
    page.wait_for_timeout(2000)
    page.screenshot(path=str(out / 'reference-intro-3550.png'))
    print('reference_captured', page.title())
    browser.close()
