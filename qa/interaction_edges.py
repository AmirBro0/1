import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
key=next(x.split('=',1)[1] for x in (root/'.env').read_text(encoding='utf-8-sig').splitlines() if x.startswith('API_KEY='))
errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1366,'height':768})
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.route('**/assets/worlds/nether.png',lambda route:route.abort())
    page.add_init_script("AudioContext.prototype.resume=function(){return Promise.reject(new Error('QA autoplay blocked'));}")
    page.goto('http://127.0.0.1:8765/',wait_until='networkidle')
    page.locator('#start-button').click()
    assert page.locator('#api-key').evaluate('(input)=>!input.validity.valid')
    page.locator('#sound-toggle').click()
    page.locator('#api-key').fill(key);page.locator('#start-button').click()
    page.locator('#portal-transition').wait_for(state='visible')
    page.locator('#skip-transition').click();page.locator('#workspace-scene').wait_for(state='visible')
    assert page.locator('#portal-transition').is_hidden()
    page.locator('#back-button').click();page.locator('#portal-transition').wait_for(state='visible')
    page.evaluate('history.back()')
    page.wait_for_timeout(2250)
    assert page.evaluate("document.documentElement.dataset.world==='nether'")
    assert page.locator('#portal-transition').is_hidden()
    page.locator('#motion-toggle').click()
    assert page.evaluate("document.documentElement.classList.contains('motion-off')")
    page.locator('#video-file').set_input_files(str(root/'qa/unsupported.mov'))
    page.locator('#playback-error').wait_for(state='visible')
    assert page.locator('#analyze-button').is_enabled()
    assert 'кодек' in page.locator('#playback-error').inner_text()
    assert errors==[],errors
    print(json.dumps({'navigation_audio_codec_edges':'passed','browser_errors':errors}))
    browser.close()
