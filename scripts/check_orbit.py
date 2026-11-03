#!/usr/bin/env python3
"""Watch the Home ring actually move: frames over time, depth, the search bar, input and fallback.

Saves a frame sequence and fails loudly if the ring does not rotate, chips lose their depth,
any chip covers the search bar, the console reports errors, or the reduced-motion grid breaks.

Usage:
    python scripts/check_orbit.py --site .capture/site --out .capture/orbit
"""

import argparse
import json
import os
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capture_site import serve  # noqa: E402

FRAME_JS = """() => {
  const bar = document.getElementById('globalSearchBox').getBoundingClientRect();
  const stageZ = 50;
  const chips = [...document.querySelectorAll('.orbit-slot:not([hidden])')].map(el => {
    const r = el.getBoundingClientRect();
    const covers = r.left < bar.right && r.right > bar.left && r.top < bar.bottom && r.bottom > bar.top;
    return {
      symbol: el.dataset.symbol,
      x: r.left + r.width / 2,
      y: r.top + r.height / 2,
      w: r.width,
      opacity: Number(getComputedStyle(el).opacity),
      z: Number(getComputedStyle(el).zIndex) || 0,
      blur: getComputedStyle(el).filter,
      covers: covers && (Number(getComputedStyle(el).zIndex) || 0) > stageZ,
    };
  });
  return { chips, bar: { top: bar.top, bottom: bar.bottom, left: bar.left, right: bar.right },
           overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth };
}"""

FPS_JS = """() => new Promise(done => {
  let n = 0; const t0 = performance.now();
  const tick = () => { n += 1; performance.now() - t0 < 2000 ? requestAnimationFrame(tick) : done(n / 2); };
  requestAnimationFrame(tick);
})"""


def check_viewport(browser, base, out, width, height, scheme, touch, problems):
    tag = f"{width}-{scheme}"
    ctx = browser.new_context(viewport={"width": width, "height": height}, has_touch=touch,
                              is_mobile=touch, device_scale_factor=2 if touch else 1)
    ctx.add_init_script(f"try{{localStorage.setItem('stockpulse_theme','{scheme}')}}catch(e){{}}")
    ctx.route("**/api/lookup*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"found": False, "message": "No demo data for this ticker."})))
    page = ctx.new_page()
    page.on("console", lambda m: problems.append(f"{tag} console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: problems.append(f"{tag} pageerror: {e}"))
    page.goto(f"{base}/index.html", wait_until="networkidle")
    page.evaluate("document.fonts.ready")

    frames = []
    for i in range(8):
        page.wait_for_timeout(750)
        frames.append(page.evaluate(FRAME_JS))
        page.screenshot(path=os.path.join(out, f"{tag}-frame{i}.jpg"), type="jpeg", quality=85)

    first, last = frames[0]["chips"], frames[-1]["chips"]
    moved = sum(1 for a, b in zip(first, last) if abs(a["x"] - b["x"]) + abs(a["y"] - b["y"]) > 8)
    if moved < len(first) * 0.7:
        problems.append(f"{tag} ring did not rotate: only {moved}/{len(first)} chips moved")
    widths = [c["w"] for f in frames for c in f["chips"]]
    if max(widths) / min(widths) < 1.7:
        problems.append(f"{tag} no visible depth: chip widths {min(widths):.0f}-{max(widths):.0f}")
    for i, frame in enumerate(frames):
        for chip in frame["chips"]:
            if chip["covers"]:
                problems.append(f"{tag} frame {i}: {chip['symbol']} covers the search bar")
        if frame["overflow"] > 0:
            problems.append(f"{tag} frame {i}: horizontal overflow {frame['overflow']}px")

    fps = page.evaluate(FPS_JS)
    print(f"{tag}: chips={len(first)} moved={moved} width {min(widths):.0f}-{max(widths):.0f}px fps={fps:.0f}")
    if fps < 30:
        problems.append(f"{tag} frame rate is only {fps:.0f} fps")

    # Typing swings the match to the front and dims the rest.
    box = page.locator("#globalSearchInput")
    box.click()
    box.press_sequentially(first[-1]["symbol"], delay=40)
    page.wait_for_timeout(1600)
    typed = page.evaluate(FRAME_JS)
    page.screenshot(path=os.path.join(out, f"{tag}-typing.jpg"), type="jpeg", quality=85)
    target = next((c for c in typed["chips"] if c["symbol"] == first[-1]["symbol"]), None)
    if not target or target["w"] < max(c["w"] for c in typed["chips"]) - 1:
        problems.append(f"{tag} search did not swing {first[-1]['symbol']} to the front")
    if not page.locator("#liveSearchResults a").first.is_visible():
        problems.append(f"{tag} search results are not visible")
    dropdown = page.evaluate("document.getElementById('searchDropdown').getBoundingClientRect().bottom")
    if target and target["y"] < dropdown:
        problems.append(f"{tag} results panel hides the matching chip")
    if target and target["y"] + target["w"] * 0.3 > height:
        problems.append(f"{tag} the matching chip is pushed below the screen (y={target['y']:.0f})")
    box.press("Enter")
    page.wait_for_load_state("domcontentloaded")
    if "company.html" not in page.url:
        problems.append(f"{tag} Enter did not open the first result: {page.url}")
    ctx.close()


def check_interaction(browser, base, problems):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(f"{base}/index.html", wait_until="networkidle")
    page.wait_for_timeout(300)

    # Hovering a chip pauses the ring.
    front = page.evaluate(FRAME_JS)["chips"]
    chip = max(front, key=lambda c: c["w"])
    page.mouse.move(chip["x"], chip["y"])
    page.wait_for_timeout(400)
    before = page.evaluate(FRAME_JS)["chips"]
    page.wait_for_timeout(800)
    after = page.evaluate(FRAME_JS)["chips"]
    drift = max(abs(a["x"] - b["x"]) for a, b in zip(before, after))
    if drift > 3:
        problems.append(f"hover did not pause the ring: drifted {drift:.1f}px")

    # A drag spins it, keeps going a little after release, and does not open the chip.
    url = page.url
    bar_y = page.evaluate(FRAME_JS)["bar"]["bottom"] + 110
    page.mouse.move(200, bar_y)
    page.wait_for_timeout(100)
    pre = page.evaluate(FRAME_JS)["chips"]
    page.mouse.down()
    page.mouse.move(420, bar_y, steps=6)
    page.mouse.move(640, bar_y, steps=6)
    page.mouse.up()
    post = page.evaluate(FRAME_JS)["chips"]
    page.wait_for_timeout(300)
    coast = page.evaluate(FRAME_JS)["chips"]
    if max(abs(a["x"] - b["x"]) for a, b in zip(pre, post)) < 40:
        problems.append("drag did not spin the ring")
    if max(abs(a["x"] - b["x"]) for a, b in zip(post, coast)) < 2:
        problems.append("no inertia after the drag")
    if page.url != url:
        problems.append(f"drag navigated away to {page.url}")

    # Wheel input scrolls the page rather than the ring.
    page.mouse.move(720, 500)
    page.mouse.wheel(0, 600)
    page.wait_for_timeout(400)
    if page.evaluate("window.scrollY") < 300:
        problems.append("the ring hijacked page scroll")
    page.evaluate("window.scrollTo(0, 0)")

    # Arrow keys rotate when a chip has focus.
    page.locator(".orbit-slot:not([hidden]) a").first.focus()
    page.wait_for_timeout(900)
    focused = page.evaluate("document.activeElement.textContent.trim().split(/\\s+/)[0]")
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(900)
    moved_to = page.evaluate("document.activeElement.textContent.trim().split(/\\s+/)[0]")
    if focused == moved_to:
        problems.append("arrow key did not move along the ring")
    ctx.close()


def check_fallback(browser, base, out, problems):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    page = ctx.new_page()
    page.goto(f"{base}/index.html", wait_until="networkidle")
    state = page.evaluate("""() => {
      const a = [...document.querySelectorAll('.orbit-slot:not([hidden])')];
      return { isStatic: document.getElementById('heroOrbitStage').classList.contains('orbit-static'),
               transformed: a.filter(e => e.style.transform).length, count: a.length,
               dust: getComputedStyle(document.getElementById('orbitDust')).display };
    }""")
    if not state["isStatic"] or state["transformed"] or state["dust"] != "none":
        problems.append(f"reduced motion should show a static grid: {state}")
    page.screenshot(path=os.path.join(out, "reduced-motion.jpg"), type="jpeg", quality=85)
    ctx.close()

    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, java_script_enabled=False)
    page = ctx.new_page()
    page.goto(f"{base}/index.html", wait_until="domcontentloaded")
    if page.locator(".orbit-slot:not([hidden]) a").count() != 12:
        problems.append("without JavaScript the 12 company links should still be there")
    ctx.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default=".capture/site")
    parser.add_argument("--out", default=".capture/orbit")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    httpd = serve(os.path.abspath(args.site))
    base_url = f"http://127.0.0.1:{httpd.server_address[1]}"
    found = []
    with sync_playwright() as p:
        chrome = p.chromium.launch(channel="chrome", headless=True)
        check_viewport(chrome, base_url, args.out, 1440, 900, "dark", False, found)
        check_viewport(chrome, base_url, args.out, 1440, 900, "light", False, found)
        check_viewport(chrome, base_url, args.out, 390, 844, "dark", True, found)
        check_interaction(chrome, base_url, found)
        check_fallback(chrome, base_url, args.out, found)
        chrome.close()
    httpd.shutdown()
    print(f"problems: {len(found)}")
    for problem in found:
        print(" -", problem)
    sys.exit(1 if found else 0)
