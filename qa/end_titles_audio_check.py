"""Check the supplied End/titles M4A files in Edge without a key or video upload."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8766")
    args = parser.parse_args()
    assert urlsplit(args.url).hostname in ("127.0.0.1", "localhost")
    report = {"checks": [], "errors": [], "media_errors": [], "tracks": {}}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page()
        posts = []
        page.on("pageerror", lambda error: report["errors"].append(str(error)))
        page.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
        page.on("response", lambda response: report["media_errors"].append(response.url) if ".m4a" in response.url and response.status >= 400 else None)
        page.route("**/audio-qa", lambda route: route.fulfill(content_type="text/html", body="""<!doctype html><meta charset="utf-8">
          <button id="enable">Enable sound</button><script type="module">
          import {AudioManager} from '/static/audio.js';
          window.audio = new AudioManager(); audio.setWorld('end');
          document.getElementById('enable').onclick=()=>audio.setEnabled(true);
          window.ready=true;</script>"""))
        page.goto(args.url.rstrip("/") + "/audio-qa")
        page.wait_for_function("window.ready")
        assert page.locator("audio").count() == 0
        assert page.evaluate("!audio.enabled && !audio.unlocked")
        report["checks"].append("muted by default, no music fetched before a sound gesture")
        page.locator("#enable").click()

        def settled(world, expected):
            page.wait_for_function("""([world,expected])=>{
              const entry=audio.music.get(world);
              return entry && !entry.element.paused && !entry.envelope && entry.element.currentTime>.3 && Math.abs(entry.element.volume-expected)<.00001;
            }""", arg=[world, expected], timeout=15000)
            return page.evaluate("""world=>{
              const element=audio.music.get(world).element;
              return {volume:element.volume,duration:element.duration,readyState:element.readyState,currentTime:element.currentTime,playbackRate:element.playbackRate};
            }""", world)

        report["tracks"]["end"] = settled("end", .08)
        assert report["tracks"]["end"]["duration"] > 1
        assert report["tracks"]["end"]["playbackRate"] == 1
        report["checks"].append("actual End M4A decodes and fades to 8%")
        page.evaluate("audio.setWorld('credits')")
        report["tracks"]["titles"] = settled("credits", .10)
        assert page.evaluate("audio.music.get('end').element.paused && audio.music.get('end').element.volume===0")
        assert report["tracks"]["titles"]["duration"] > 1
        report["checks"].append("actual titles M4A decodes and fades to 10%; outgoing End stops")
        page.evaluate("audio.setCreditsPaused(true)")
        assert page.evaluate("[...audio.music.values()].every(e=>e.element.paused&&e.element.volume===0)")
        page.wait_for_timeout(200)
        page.evaluate("audio.setCreditsPaused(false)")
        settled("credits", .10)
        report["checks"].append("credits pause immediately silences music; resume restores 10%")
        page.evaluate("audio.duck(true)")
        settled("credits", .03)
        page.evaluate("audio.duck(false)")
        settled("credits", .10)
        page.evaluate("audio.setWorld('end')")
        settled("end", .08)
        page.evaluate("audio.duck(true)")
        settled("end", .024)
        page.evaluate("audio.duck(false)")
        settled("end", .08)
        report["checks"].append("single volume stage: video duck multiplier .30 gives .024 End/.03 titles and restores")
        page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'))")
        saved = page.evaluate("audio.music.get('end').element.currentTime")
        page.wait_for_timeout(250)
        assert page.evaluate("[...audio.music.values()].every(e=>e.element.paused&&e.element.volume===0)")
        assert abs(page.evaluate("audio.music.get('end').element.currentTime") - saved) < .02
        page.evaluate("delete document.hidden;document.dispatchEvent(new Event('visibilitychange'))")
        settled("end", .08)
        report["checks"].append("visibility event stops playback and restores the same End position/level")
        page.evaluate("audio.setEnabled(false)")
        assert page.evaluate("[...audio.music.values()].every(e=>e.element.paused&&e.element.volume===0)")
        page.locator("#enable").click()
        settled("end", .08)
        report["checks"].append("global mute cancels playback/fades; unmute restores 8%")
        levels = page.evaluate("""()=>{
          const original=audio.userVolume;
          const normal={overworld:audio.level('overworld'),nether:audio.level('nether')};
          audio.userVolume=.02;
          const quiet={end:audio.level('end'),credits:audio.level('credits')};
          audio.userVolume=original;
          return {normal,quiet};
        }""")
        assert levels["normal"] == {"overworld": .10, "nether": .0841395}
        assert levels["quiet"] == {"end": .02, "credits": .02}
        report["checks"].append("old world balance unchanged; quieter saved preference remains a ceiling")
        assert not posts, posts
        assert not report["errors"], report["errors"]
        assert not report["media_errors"], report["media_errors"]
        browser.close()
    for name in ("end", "titles"):
        report["tracks"][name]["sha256"] = hashlib.sha256((ROOT / f"web/assets/music/{name}.m4a").read_bytes()).hexdigest()
    (ROOT / "qa/end-titles-audio-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
