"""Synthetic browser-only regression for Nether / End portal travel."""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8766/#analysis'
CAPS = {'capabilities': {'formats': ['.mov'], 'max_upload_bytes': 104857600, 'deadline_sec': 300}}
MONITOR = r'''() => {
 const portal=document.getElementById('portal-transition');
 const canvas=document.getElementById('portal-canvas');
 const ctx=canvas.getContext('2d');
 const audit=window.portalAudit={start:performance.now(),samples:[],seen:false,done:false};
 let last=0;
 function sample(t) {
   if (t-last<35) {requestAnimationFrame(sample);return;} last=t;
   const visible=!portal.hidden;
   if (visible) audit.seen=true;
   const d=ctx.getImageData(0,0,canvas.width,canvas.height).data;
   const colors=new Set();let painted=0;
   for(let i=0;i<d.length;i+=64){if(d[i+3]>0){painted++;colors.add(`${d[i]},${d[i+1]},${d[i+2]}`);}}
   audit.samples.push({ms:Math.round(t-audit.start),visible,phase:portal.dataset.phase,world:document.documentElement.dataset.world,colors:colors.size,painted});
   if(audit.seen&&!visible){audit.done=true;return;}
   requestAnimationFrame(sample);
 } requestAnimationFrame(sample);
}'''

async def fixture(route):
 path=route.request.url.split('/ui/v1/',1)[1]
 if route.request.method != 'GET':
  raise AssertionError('Unexpected write in portal test')
 if path == 'session':
  payload=CAPS
 elif path.startswith('runs?'):
  payload={'items': [], 'total': 0}
 else:
  raise AssertionError('Unexpected UI endpoint: '+path)
 await route.fulfill(status=200,content_type='application/json',body=json.dumps(payload))

async def ready(page):
 await page.goto(URL,wait_until='domcontentloaded')
 await page.wait_for_function("document.documentElement.dataset.world==='nether' && document.getElementById('portal-transition').hidden")
 await page.wait_for_timeout(80)

async def transition(page,selector,destination,*,skip=False,screenshot=False,reduced=False):
 await page.evaluate(MONITOR)
 await page.locator(selector).click()
 if screenshot:
  await page.wait_for_function("document.getElementById('portal-transition').dataset.phase==='crossing'")
  await page.screenshot(path=str(ROOT/'end-portal-restored.png'))
 if skip:
  await page.wait_for_function("document.getElementById('portal-transition').dataset.phase==='approach'")
  await page.locator('#skip-transition').click()
 await page.wait_for_function('window.portalAudit.done')
 audit=await page.evaluate('window.portalAudit')
 samples=audit['samples'];visible=[s for s in samples if s['visible']]
 phases=list(dict.fromkeys(s['phase'] for s in visible))
 elapsed=samples[-1]['ms']-visible[0]['ms']
 world=await page.locator('html').get_attribute('data-world')
 assert world==destination,(world,destination)
 assert visible, 'No visible transition overlay'
 if reduced:
  assert elapsed<700,elapsed
  assert not any(s['phase'] in ['approach','crossing','destination'] for s in visible),phases
  assert max(s['colors'] for s in visible)<=1, 'Reduced motion should only use a uniform fade'
 elif skip:
  assert elapsed<1500,elapsed
 else:
  assert 1800<=elapsed<=2800,elapsed
  assert all(x in phases for x in ['approach','crossing','destination']),phases
  assert max(s['colors'] for s in visible)>=8,'Expected stepped portal waves'
 return {'destination':world,'duration_ms':elapsed,'phases':phases,'max_colors':max(s['colors'] for s in visible),'skip':skip,'reduced':reduced,'passed':True}

async def main():
 results=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(channel='chrome',headless=True)
  for width,height,reduced in [(1366,768,False),(390,844,False),(1366,768,True)]:
   context=await browser.new_context(viewport={'width':width,'height':height},reduced_motion='reduce' if reduced else 'no-preference')
   page=await context.new_page();errors=[]
   page.on('pageerror',lambda e:errors.append(str(e)))
   await page.route('**/ui/v1/**',fixture)
   await ready(page)
   cases=[await transition(page,'#nav-history','end',screenshot=width==1366 and not reduced,reduced=reduced),await transition(page,'#back-button','nether',reduced=reduced)]
   if not reduced:
    cases.append(await transition(page,'#nav-history','end',skip=True))
   assert not errors,errors
   results.append({'viewport':[width,height],'reduced_motion':reduced,'cases':cases,'errors':errors})
   await context.close()
  await browser.close()
 output={'synthetic_api_only':True,'cases_passed':sum(len(r['cases']) for r in results),'results':results}
 (ROOT/'end-portal-restored-results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(output,ensure_ascii=True,indent=2))

if __name__ == '__main__':
 asyncio.run(main())
