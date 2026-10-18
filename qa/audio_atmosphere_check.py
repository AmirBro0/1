"""Real local media playback and visual timeline checks; no model inference is simulated here."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
key=next(x.split('=',1)[1] for x in (root/'.env').read_text(encoding='utf-8-sig').splitlines() if x.startswith('API_KEY='))
report={'errors':[], 'checks':[]}
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
    page=browser.new_page(viewport={'width':1366,'height':768})
    page.on('pageerror',lambda error:report['errors'].append(str(error)))
    posts=[]
    page.on('request',lambda request:posts.append(request.url) if request.method=='POST' else None)
    page.add_init_script("""window.qaFirstPlay=[];const play=HTMLMediaElement.prototype.play;
      HTMLMediaElement.prototype.play=function(){if(this.tagName==='AUDIO')qaFirstPlay.push({world:this.dataset.world,volume:this.volume});return play.call(this);};
    """)
    page.goto('http://127.0.0.1:8765/',wait_until='networkidle')
    page.evaluate("""async()=> {
      const {Worlds}=await import('/static/worlds.js');
      const original=Worlds.prototype.go;
      Worlds.prototype.go=function(...args){window.qaWorlds=this;return original.apply(this,args);};
      const {AudioManager}=await import('/static/audio.js');
      const enable=AudioManager.prototype.setEnabled;
      AudioManager.prototype.setEnabled=function(...args){window.qaAudio=this;return enable.apply(this,args);};
    }""")
    page.locator('#sound-toggle').click()
    page.wait_for_function("document.querySelector('audio[data-world=overworld]')?.currentTime>.5")
    page.wait_for_timeout(1400)
    assert page.evaluate("document.querySelector('audio').volume<=.10001")
    assert page.evaluate("qaFirstPlay[0].volume===0")
    assert page.evaluate("document.querySelector('audio').duration>208")
    report['checks'].append('real M4A playback, zero first volume, fade to .10')
    page.locator('#api-key').fill(key)
    page.locator('#start-button').click()
    page.locator('#portal-transition').wait_for(state='visible')
    page.wait_for_timeout(360)
    page.screenshot(path=str(root/'qa/portal-approach.png'))
    assert not page.locator('#workspace-scene').evaluate("(e)=>e.classList.contains('upload-assembling')")
    page.wait_for_timeout(550)
    page.screenshot(path=str(root/'qa/portal-crossing.png'))
    page.wait_for_timeout(500)
    assert page.locator('#workspace-scene').is_visible()
    assert not page.locator('#workspace-scene').evaluate("(e)=>e.classList.contains('upload-assembling')")
    page.locator('#portal-transition').wait_for(state='hidden')
    assert page.locator('#workspace-scene').evaluate("(e)=>e.classList.contains('upload-assembling')")
    page.wait_for_timeout(1300)
    assert page.evaluate("document.querySelector('audio[data-world=overworld]').paused")
    assert page.evaluate("document.querySelector('audio[data-world=nether]').currentTime>1")
    assert page.evaluate("Math.abs(document.querySelector('audio[data-world=nether]').volume-.0841395)<.001")
    assert page.evaluate("qaAudio.localSounds?.get('portal').event==='block.portal.travel'")
    report['checks'].append('2s portal, original private SFX decoded, UPLOAD only after finish, Nether gain')
    page.locator('#video-file').set_input_files(str(root/'qa/sample.mov'))
    page.wait_for_function("document.getElementById('video').readyState>=2")
    page.locator('#play-button').click();page.wait_for_timeout(500)
    assert page.evaluate("document.querySelector('audio[data-world=nether]').volume<=.03001")
    assert page.evaluate("document.getElementById('video').volume===1")
    page.locator('#play-button').click();page.wait_for_timeout(850)
    assert page.evaluate("document.querySelector('audio[data-world=nether]').volume>.08")
    report['checks'].append('video duck <= .03, restore, independent video audio')
    page.locator('#play-button').click();page.wait_for_timeout(370)
    page.locator('#sound-toggle').click();page.wait_for_timeout(1300)
    assert page.evaluate("[...document.querySelectorAll('audio')].every(a=>a.paused&&a.volume===0)")
    page.locator('#play-button').click()
    page.locator('#sound-toggle').click();page.wait_for_timeout(1500)
    assert page.evaluate("document.querySelector('audio[data-world=nether]').volume>.08")
    report['checks'].append('mute cancels fades during video, unmute resumes correct track')
    # Observe ash/sparks for 26s, all UI exclusion pixels must remain transparent.
    page.evaluate("window.qaFx=[];window.qaSampler=setInterval(()=>qaFx.push({counts:qaWorlds.particles.reduce((o,p)=>(o[p.type]=(o[p.type]||0)+1,o),{}),blocked:qaWorlds.blocked.length}),1000)")
    page.wait_for_timeout(26000)
    page.evaluate("clearInterval(qaSampler)")
    assert page.evaluate("qaFx.every(x=>(x.counts.ash||0)<=6&&(x.counts.spark||0)<=2)")
    assert page.evaluate("""()=>{
      const c=qaWorlds.fx, W=c.canvas.width,H=c.canvas.height;
      return qaWorlds.blocked.every(r=>{
        const x=Math.max(0,Math.ceil(r.x)),y=Math.max(0,Math.ceil(r.y));
        const w=Math.min(W-x,Math.floor(r.w)),h=Math.min(H-y,Math.floor(r.h));
        if(w<=0||h<=0)return true;
        const d=c.getImageData(x,y,w,h).data;return d.every((v,i)=>i%4!==3||v===0);
      });
    }""")
    page.screenshot(path=str(root/'qa/refined-nether.png'))
    report['nether_observation_seconds']=26
    report['nether_max_observed']={t:page.evaluate(f"Math.max(...qaFx.map(x=>x.counts.{t}||0))") for t in ['ash','spark']}
    assert page.evaluate('qaWorlds.lava.length>100')
    saved=page.evaluate("document.querySelector('audio[data-world=nether]').currentTime")
    page.locator('#back-button').click()
    page.locator('#portal-transition').wait_for(state='hidden')
    page.wait_for_timeout(1300)
    assert page.locator('#welcome-scene').is_visible()
    page.wait_for_timeout(26000)
    assert page.evaluate("qaWorlds.foliage.every(t=>t.count>100)")
    assert page.evaluate("qaWorlds.particles.length<=6")
    page.screenshot(path=str(root/'qa/refined-overworld.png'))
    report['overworld_observation_seconds']=26
    report['canopy_mask_pixels']=page.evaluate('qaWorlds.foliage.map(t=>t.count)')
    page.locator('#start-button').click();page.locator('#portal-transition').wait_for(state='hidden')
    page.wait_for_timeout(1200)
    assert page.evaluate("document.querySelector('audio[data-world=nether]').currentTime")>saved
    assert page.evaluate("document.querySelectorAll('audio').length===2")
    report['checks'].append('26s each world, sparse particles, protected panels, canopy masks, saved position, 2 instances')
    # Exercise loop boundary without waiting five minutes for the whole track.
    page.evaluate("const a=document.querySelector('audio[data-world=nether]');a.currentTime=a.duration-.10")
    page.wait_for_timeout(850)
    assert page.evaluate("document.querySelector('audio[data-world=nether]').currentTime<2")
    assert page.evaluate("document.querySelector('audio[data-world=nether]').volume<=.08414")
    # Deterministically emulate visibility; verify positions stop and resume.
    page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'))")
    before=page.evaluate("document.querySelector('audio[data-world=nether]').currentTime")
    page.wait_for_timeout(400)
    assert page.evaluate("[...document.querySelectorAll('audio')].every(a=>a.paused&&a.volume===0)")
    assert abs(page.evaluate("document.querySelector('audio[data-world=nether]').currentTime")-before)<.02
    page.evaluate("delete document.hidden;document.dispatchEvent(new Event('visibilitychange'))")
    page.wait_for_timeout(1300)
    assert page.evaluate("document.querySelector('audio[data-world=nether]').currentTime")>before
    # Cancel and mute mid-transition.
    page.locator('#back-button').click();page.wait_for_timeout(300)
    page.locator('#portal-sound-toggle').click()
    page.locator('#skip-transition').click()
    page.wait_for_timeout(1300)
    assert page.evaluate("[...document.querySelectorAll('audio')].every(a=>a.paused&&a.volume===0)")
    assert page.evaluate("qaAudio.active.size===0")
    page.locator('#sound-toggle').click()
    page.locator('#start-button').click();page.wait_for_timeout(300)
    page.evaluate("document.getElementById('brand-link').click()")
    page.locator('#portal-transition').wait_for(state='hidden')
    assert page.locator('#welcome-scene').is_visible()
    assert page.evaluate("location.hash==='#welcome'")
    assert len(posts)==0
    report['checks'].append('loop envelope, hidden tab pause/resume, skip+mute mid-portal, rapid reverse, zero analysis POST')
    page.emulate_media(reduced_motion='reduce')
    page.locator('#start-button').click();page.locator('#portal-transition').wait_for(state='hidden')
    assert page.locator('#workspace-scene').is_visible()
    assert page.evaluate("qaWorlds.particles.length===0")
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    page.emulate_media(reduced_motion='no-preference');page.wait_for_timeout(1200)
    assert page.evaluate("qaWorlds.particles.length<=4")
    report['checks'].append('reduced motion calm transition and mobile resize')
    # A missing track fails once and does not repeatedly fetch on navigation.
    missing=browser.new_page()
    failures=[]
    missing.route('**/assets/music/netherworld.m4a',lambda route:(failures.append(route.request.url),route.fulfill(status=404)))
    missing.goto('http://127.0.0.1:8765/',wait_until='networkidle')
    missing.locator('#sound-toggle').click()
    missing.locator('#api-key').fill(key);missing.locator('#start-button').click()
    missing.wait_for_function("document.documentElement.dataset.world==='nether' && document.getElementById('portal-transition').hidden")
    missing.wait_for_function("document.querySelector('audio[data-world=nether]')?.dataset.unavailable==='true'")
    missing.locator('#back-button').click();missing.wait_for_function("document.documentElement.dataset.world==='overworld' && document.getElementById('portal-transition').hidden")
    missing.locator('#start-button').click();missing.wait_for_function("document.documentElement.dataset.world==='nether' && document.getElementById('portal-transition').hidden")
    assert len(failures)==1,failures
    assert missing.locator('#workspace-scene').is_visible()
    report['checks'].append('missing track requested once, app still usable')
    quiet=browser.new_page(reduced_motion='reduce')
    quiet.add_init_script("localStorage.setItem('site-music-volume','.02');localStorage.setItem('site-sound','on')")
    quiet.goto('http://127.0.0.1:8765/',wait_until='networkidle')
    assert quiet.locator('audio').count()==0
    quiet.locator('#api-key').fill(key);quiet.locator('#start-button').click()
    quiet.locator('#workspace-scene').wait_for(state='visible');quiet.wait_for_timeout(1600)
    quiet.locator('#video-file').set_input_files(str(root/'qa/sample.mov'))
    quiet.wait_for_function("document.getElementById('video').readyState>=2")
    quiet.locator('#play-button').click();quiet.wait_for_timeout(450)
    assert quiet.evaluate("document.querySelector('audio[data-world=nether]').volume<.02")
    assert quiet.evaluate("document.querySelector('audio[data-world=nether]').playbackRate===1")
    report['checks'].append('saved quieter volume is not raised to .03, no autoplay before gesture, original playback rate')
    assert report['errors']==[],report['errors']
    (root/'qa/atmosphere_audio_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))
    browser.close()

