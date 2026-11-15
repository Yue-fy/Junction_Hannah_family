"""V5 lane FC: screenshots of the 30-day balance chart at 375/390/768/1280 (not run by unittest).

Usage: python3 tests/browser/forecast_v5_shots.py <tag> [persona] [en|fi|sv] [WxH,...]
Needs a server on :8301 and Google Chrome; writes PNGs to /tmp/fc/shots (idle and with the day readout open).
"""
import os, sys, asyncio
from playwright.async_api import async_playwright
SIZES=[(375,812),(390,844),(768,1024),(1280,800)]
tag=sys.argv[1]; persona=sys.argv[2] if len(sys.argv)>2 else 'CUST00001'; lang=sys.argv[3] if len(sys.argv)>3 else 'en'
sizes=SIZES if len(sys.argv)<=4 else [tuple(map(int,s.split('x'))) for s in sys.argv[4].split(',')]
async def main():
  async with async_playwright() as p:
    b=await p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox'])
    for w,h in sizes:
      ctx=await b.new_context(viewport={'width':w,'height':h},device_scale_factor=2,has_touch=w<700,is_mobile=w<700)
      await ctx.add_init_script(f"localStorage.setItem('scoach.locale','{lang}');")
      pg=await ctx.new_page(); errs=[]
      pg.on('console',lambda m: errs.append(m.text) if m.type=='error' else None)
      pg.on('pageerror',lambda e: errs.append(str(e)))
      await pg.goto('http://localhost:8301/#spending'); await pg.wait_for_timeout(1500)
      if persona!='CUST00001':
        await pg.evaluate(f"(()=>{{const s=document.getElementById('persona');s.value='{persona}';s.dispatchEvent(new Event('change'))}})()"); await pg.wait_for_timeout(1500)
        await pg.evaluate("location.hash='#spending'"); await pg.wait_for_timeout(800)
      await pg.evaluate("document.getElementById('forecast-analysis').open=true"); await pg.wait_for_timeout(600)
      card=pg.locator('#trends-view .preview-card')
      await card.scroll_into_view_if_needed(); await pg.wait_for_timeout(300)
      await card.screenshot(path=f'/tmp/fc/shots/{tag}-{persona}-{lang}-{w}.png')
      # tooltip probe
      svg=pg.locator('#runway-chart svg').first
      bb=await svg.bounding_box()
      if bb:
        if w<700: await pg.touchscreen.tap(bb['x']+bb['width']*0.62,bb['y']+bb['height']*0.4)
        else: await pg.mouse.move(bb['x']+bb['width']*0.62,bb['y']+bb['height']*0.4)
        await pg.wait_for_timeout(300)
        await card.screenshot(path=f'/tmp/fc/shots/{tag}-{persona}-{lang}-{w}-tip.png')
      await pg.screenshot(path=f'/tmp/fc/shots/{tag}-{persona}-{lang}-{w}-viewport.png')
      ow=await pg.evaluate("document.documentElement.scrollWidth>window.innerWidth")
      print(w,'errors',errs[:3],'overflow',ow)
      await ctx.close()
    await b.close()
asyncio.run(main())
