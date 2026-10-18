"""Screenshot regressions for the requested UI corrections, with isolated data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'qa'
URL = 'http://127.0.0.1:8767'
KEY = 'forte-ui-refresh-isolated-test-key-2026'


def main():
    portrait = OUT / 'fixtures' / 'portrait.mov'
    if not portrait.exists():
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc2=size=320x640:rate=10', '-t', '8',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(portrait)], check=True)
    env = {**os.environ, 'API_KEY': KEY, 'DATA_DIR': str(OUT / 'ui-refresh-runtime'),
           'ENABLE_TEAM_MODEL': '0', 'MODEL_COMMAND_JSON': '[]', 'EMBEDDED_WORKER': '1'}
    log = (OUT / 'ui-refresh-server.log').open('w', encoding='utf-8')
    server = subprocess.Popen([sys.executable, '-m', 'app', '--port', '8767'], cwd=ROOT,
                              env=env, stdout=log, stderr=log, creationflags=0x08000000)
    checks, errors, missing = [], [], []
    try:
        for _ in range(60):
            try:
                with urlopen(URL + '/health', timeout=1) as response:
                    assert response.status == 200
                break
            except OSError:
                time.sleep(.25)
        else:
            raise AssertionError('QA server did not start')
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='msedge', headless=True)
            context = browser.new_context(viewport={'width': 1366, 'height': 900}, reduced_motion='reduce')
            page = context.new_page()
            # Check deployment compatibility with an already-running pre-scope API.
            def legacy_scope_response(route):
                response = route.fetch()
                value = response.json()
                if isinstance(value, dict):
                    value.pop('analysis_scope', None)
                    if isinstance(value.get('result'), dict):
                        value['result'].pop('analysis_scope', None)
                route.fulfill(response=response, json=value)
            page.route('**/ui/v1/session', legacy_scope_response)
            page.route('**/ui/v1/jobs/*', legacy_scope_response)
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('response', lambda response: missing.append(response.url) if response.status == 404 else None)
            page.goto(URL, wait_until='networkidle')
            page.screenshot(path=str(OUT / 'refresh-overworld.png'), full_page=True)
            assert page.locator('.nav-links').count() == 0
            checks.append('text-navigation-removed')
            page.locator('#api-key').fill(KEY)
            page.locator('#start-button').click()
            page.locator('#workspace-scene').wait_for(state='visible')
            page.locator('#portal-transition').wait_for(state='hidden')
            assert 'LLM не подключена' in page.locator('#analysis-scope').inner_text()
            assert 'КАМЕРУ' in page.locator('#analyze-button').inner_text()
            checks.append('camera-only-capability-is-visible')
            checks.append('compatible-with-running-pre-scope-api')
            page.locator('#video-file').set_input_files(str(portrait))
            page.locator('#analyze-button').click()
            page.locator('.report-json').wait_for(state='visible', timeout=90000)
            assert page.locator('details.report-json-details').count() == 0
            assert page.locator('.report-json').is_visible()
            assert page.locator('#report-tools').get_by_role('radio').count() == 3
            page.locator('#report-tools').get_by_role('radio').last.click()
            page.wait_for_timeout(1600)
            checks.append('permanent-api-response-and-themed-review')
            slots = page.locator('.timeline-slot')
            assert slots.count() > 0
            slots.first.scroll_into_view_if_needed()
            page.wait_for_timeout(100)
            slots.first.hover()
            tip = page.locator('.timeline-preview')
            tip.wait_for(state='visible')
            box = tip.bounding_box()
            assert box['height'] <= 230, box
            assert box['y'] >= 0 and box['y'] + box['height'] <= 901, box
            assert box['x'] >= 0 and box['x'] + box['width'] <= 1367, box
            page.screenshot(path=str(OUT / 'refresh-preview-contained.png'))
            page.screenshot(path=str(OUT / 'refresh-timeline-portrait.png'), full_page=True)
            checks.append('portrait-preview-contained')
            page.locator('#nav-history').click()
            page.locator('#archive-scene').wait_for(state='visible')
            page.locator('#portal-transition').wait_for(state='hidden')
            page.wait_for_function("!document.getElementById('archive-status').textContent.includes('Загрузка')")
            page.screenshot(path=str(OUT / 'refresh-end.png'), full_page=True)
            assert not page.locator('#archive-filter').is_visible()
            assert page.locator('.archive-controls .choice-trigger').count() == 3
            assert page.locator('#archive-refresh-button').is_visible()
            # A custom filter must open and close by keyboard without OS dropdowns.
            combo = page.locator('.archive-controls .choice-trigger').first
            combo.focus()
            combo.press('ArrowDown')
            assert page.get_by_role('listbox').is_visible()
            page.get_by_role('listbox').press('Escape')
            assert not page.get_by_role('listbox').is_visible()
            combo.press('ArrowDown')
            page.get_by_role('listbox').press('ArrowDown')
            page.get_by_role('listbox').press('Enter')
            assert page.locator('#archive-filter').input_value() == 'queued'
            combo.press('ArrowDown')
            page.get_by_role('listbox').press('Home')
            page.get_by_role('listbox').press('Enter')
            assert page.locator('#archive-filter').input_value() == 'all'
            page.locator('#archive-search').fill('portrait')
            page.wait_for_timeout(700)
            assert page.locator('.archive-card').count() >= 1
            checks.append('custom-filter-keyboard-and-search')
            page.locator('#end-exit-button').click()
            page.locator('#credits-scene').wait_for(state='visible')
            page.locator('#portal-transition').wait_for(state='hidden')
            assert not page.locator('.game-nav').is_visible()
            assert page.locator('#credits-scene').bounding_box()['y'] == 0
            page.screenshot(path=str(OUT / 'refresh-credits.png'))
            checks.append('portal-opens-fullscreen-credits-without-navbar')
            page.locator('#credits-skip').click()
            page.locator('#welcome-scene').wait_for(state='visible')
            page.locator('#portal-transition').wait_for(state='hidden')
            assert page.locator('.game-nav').is_visible()
            checks.append('credits-return-restores-hud')
            for width, height in [(1920, 1080), (390, 844)]:
                page.set_viewport_size({'width': width, 'height': height})
                page.locator('#start-button').click()
                page.locator('#workspace-scene').wait_for(state='visible')
                page.locator('#portal-transition').wait_for(state='hidden')
                page.screenshot(path=str(OUT / f'refresh-nether-{width}.png'), full_page=True)
                overflow = page.evaluate("({width:innerWidth,scroll:document.documentElement.scrollWidth,nodes:[...document.querySelectorAll('body *')].map(e=>({tag:e.tagName,id:e.id,class:e.className,x:e.getBoundingClientRect().x,right:e.getBoundingClientRect().right})).filter(e=>e.x>innerWidth||e.right>innerWidth+1).slice(0,10)})")
                assert overflow['scroll'] <= width + 1, overflow
                page.locator('#nav-history').click()
                page.locator('#archive-scene').wait_for(state='visible')
                page.locator('#portal-transition').wait_for(state='hidden')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                page.screenshot(path=str(OUT / f'refresh-end-{width}.png'), full_page=True)
                page.locator('#back-button').click()
                page.locator('#workspace-scene').wait_for(state='visible')
                page.locator('#portal-transition').wait_for(state='hidden')
                page.locator('#back-button').click()
                page.locator('#welcome-scene').wait_for(state='visible')
                page.locator('#portal-transition').wait_for(state='hidden')
            checks.append('desktop-and-mobile-layout')
            checks.append('end-back-returns-nether-before-overworld')
            browser.close()
        assert not errors, errors
        assert not missing, missing
        result = {'checks': checks, 'page_errors': errors, 'missing_assets': missing}
        (OUT / 'ui-refresh-results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
    finally:
        server.terminate()
        try:
            server.wait(timeout=8)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
        log.close()


if __name__ == '__main__':
    main()
