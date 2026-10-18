import base64
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
key=next(x.split('=',1)[1] for x in (root/'.env').read_text(encoding='utf-8-sig').splitlines() if x.startswith('API_KEY='))
frame=base64.b64encode((root/'qa/evidence.jpg').read_bytes()).decode('ascii')
events=[{'type':'Тестовый эпизод','timecode_sec':1.5,'description':'Синтетический ответ только для проверки интерфейса.','evidence_frames':[{'timestamp_sec':1.5,'image_base64':frame}], 'rule':{'document':'Тестовый источник','section':'пункт QA','url':'https://example.com'}}]
mode={'value':'events'}
requests=[]
errors=[]
music_requests=[]

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1366,'height':768},reduced_motion='reduce')
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:music_requests.append(r.url) if '/music/' in r.url else None)
    page.goto('http://127.0.0.1:8765/',wait_until='networkidle')
    page.locator('#api-key').fill(key);page.locator('#start-button').click();page.locator('#workspace-scene').wait_for(state='visible')
    page.locator('#video-file').set_input_files({'name':'invalid.txt','mimeType':'text/plain','buffer':b'not video'})
    assert 'формате .mov' in page.locator('#analysis-error').inner_text()
    page.locator('#video-file').set_input_files(str(root/'qa/sample.mov'))
    page.wait_for_function("document.getElementById('video').readyState >= 1")
    assert page.locator('#analyze-button').is_enabled()
    assert page.locator('#play-button').is_enabled()
    page.locator('#play-button').click();page.wait_for_timeout(300)
    assert page.locator('#video').evaluate('(v)=>v.currentTime')>0
    page.locator('#play-button').click()
    page.locator('#zoom-button').click();assert page.locator('#video').evaluate('(v)=>getComputedStyle(v).transform')=='matrix(2, 0, 0, 2, 0, 0)'
    page.locator('#zoom-button').click();assert not page.locator('#video').evaluate('(v)=>v.classList.contains("zoomed")')
    page.locator('#fullscreen-button').click();page.wait_for_function('document.fullscreenElement !== null')
    page.evaluate('document.exitFullscreen()')
    page.locator('#video-mute').click();assert page.locator('#video').evaluate('(v)=>v.muted')
    page.locator('#sound-toggle').click();assert page.locator('#sound-toggle').get_attribute('aria-pressed')=='true'
    page.locator('#sound-toggle').click();assert page.locator('#sound-toggle').get_attribute('aria-pressed')=='false'

    def post(route):
        requests.append('analyze')
        assert route.request.headers.get('x-api-key')==key
        assert b'sample.mov' in route.request.post_data_buffer
        if mode['value']=='http-error':route.fulfill(status=500,json={'detail':'Тестовая ошибка сервера'})
        else:route.fulfill(status=202,json={'job_id':'synthetic-ui-qa'})
    def job(route):
        if mode['value']=='failed':route.fulfill(json={'job_id':'synthetic-ui-qa','status':'failed','error':'Тестовый сбой локальной модели'});return
        selected=[] if mode['value']=='empty' else events*20 if mode['value']=='long' else events
        route.fulfill(json={'job_id':'synthetic-ui-qa','status':'done','verdict':'violation' if selected else 'no_violation','violations':selected})
    page.route('**/api/v1/analyze',post)
    page.route('**/api/v1/jobs/synthetic-ui-qa',job)
    page.locator('#analyze-button').click();page.wait_for_function("document.getElementById('event-count').textContent === '1'")
    page.locator('.event-time').first.click()
    assert abs(page.locator('#video').evaluate('(v)=>v.currentTime')-1.5)<.1
    assert len(requests)==1
    page.locator('.evidence-thumb').first.click();assert page.locator('#evidence-dialog').is_visible()
    assert page.locator('#evidence-image').evaluate('(image)=>image.naturalWidth')>0
    page.locator('#evidence-dialog [data-close]').click()
    page.locator('#back-button').click();page.locator('#welcome-scene').wait_for(state='visible')
    assert page.locator('#video').evaluate('(v)=>v.paused')
    page.locator('#start-button').click();page.locator('#workspace-scene').wait_for(state='visible')
    assert page.locator('#file-name').inner_text()=='sample.mov'
    assert page.locator('#event-count').inner_text()=='1'
    assert abs(page.locator('#video').evaluate('(v)=>v.currentTime')-1.5)<.1
    mode['value']='empty';page.locator('#analyze-button').click()
    page.wait_for_function("document.getElementById('event-count').textContent === '0'")
    assert 'Модель не отметила' in page.locator('#chat-log').inner_text()
    mode['value']='failed';page.locator('#analyze-button').click();page.locator('#analysis-error').wait_for(state='visible')
    assert 'Тестовый сбой' in page.locator('#analysis-error').inner_text()
    mode['value']='http-error';page.locator('#analyze-button').click();page.wait_for_function("document.getElementById('analysis-error').textContent.includes('ошибка сервера')")
    mode['value']='long';page.locator('#analyze-button').click();page.wait_for_function("document.getElementById('event-count').textContent === '20'")
    page.locator('#chat-log').evaluate('(e)=>e.scrollTop=0')
    page.locator('#analyze-button').click();page.wait_for_function("document.getElementById('analysis-status').dataset.state==='done'")
    assert page.locator('#chat-log').evaluate('(e)=>e.scrollTop')==0
    assert page.locator('#new-events').is_visible()
    assert all(url.endswith(('overworld.m4a','netherworld.m4a')) for url in music_requests)
    assert errors==[],errors
    page.screenshot(path=str(root/'qa/player-test-result.png'),full_page=True)
    print(json.dumps({'player_and_pipeline':'passed','analyze_requests':len(requests),'browser_errors':errors,'actual_music_requests':len(music_requests)}))
    browser.close()
