"""UI checks use explicit test responses; production contains no mock results."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
key = next(line.split('=',1)[1] for line in (root/'.env').read_text(encoding='utf-8-sig').splitlines() if line.startswith('API_KEY='))
output = root/'qa'
errors = []

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe', headless=True)
    page = browser.new_page(viewport={"width":1366,"height":768}, device_scale_factor=1)
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://127.0.0.1:8765/',wait_until='networkidle')
    page.screenshot(path=str(output/'welcome-1366.png'),full_page=True)
    page.locator('#api-key').fill('incorrect-key')
    page.locator('#start-button').click()
    page.locator('#welcome-error').wait_for(state='visible')
    assert 'Неверный' in page.locator('#welcome-error').inner_text()
    page.locator('#api-key').fill(key)
    page.locator('#start-button').click()
    page.locator('#workspace-scene').wait_for(state='visible')
    page.wait_for_timeout(2250)
    page.screenshot(path=str(output/'workspace-1366.png'),full_page=True)
    page.set_viewport_size({"width":1920,"height":1080})
    page.screenshot(path=str(output/'workspace-1920.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('#chat-log .chat-entry').count()==0
    assert page.locator('#analyze-button').is_disabled()
    assert page.evaluate("sessionStorage.getItem('api_key')===null && localStorage.getItem('api_key')===null")
    page.locator('#back-button').click()
    page.wait_for_timeout(2250)
    assert page.locator('#welcome-scene').is_visible()
    mobile=browser.new_page(viewport={"width":390,"height":844},device_scale_factor=1,reduced_motion='reduce')
    mobile.on('pageerror', lambda error: errors.append(str(error)))
    mobile.goto('http://127.0.0.1:8765/',wait_until='networkidle')
    mobile.screenshot(path=str(output/'welcome-mobile.png'),full_page=True)
    mobile.locator('#api-key').fill(key);mobile.locator('#start-button').click()
    mobile.locator('#workspace-scene').wait_for(state='visible')
    mobile.screenshot(path=str(output/'workspace-mobile.png'),full_page=True)
    print(mobile.evaluate("""Array.from(document.querySelectorAll('body *')).map(e=>({tag:e.tagName,cls:e.className?.baseVal??e.className,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width})).filter(x=>x.right>innerWidth+1&&x.width>0).slice(0,20)"""))
    assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert errors==[],errors
    print(json.dumps({'initial_checks':'passed','browser_errors':errors},ensure_ascii=True))
    browser.close()
