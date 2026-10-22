import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
P=Path(__file__).resolve().parent
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
  page=await browser.new_page(viewport={'width':1080,'height':870},device_scale_factor=1)
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  await page.set_content((P/'index.html').read_text(),wait_until='load',timeout=45000)
  print('Title:',await page.title(),'A/B buttons:',await page.locator('button[data-play]').count(),flush=True)
  await page.screenshot(path=str(P/'screenshot_v4.png'),full_page=True)
  await page.evaluate('async () => {audioCtx=new AudioContext(); await audioCtx.resume()}')
  for mode in ['reference','v3','firmware','lpc1','lpc2','full']:
   try:
    r=await page.evaluate('async (mode)=>{const r=await decode(mode);return{samples:r.data.length,sampleRate:r.sr,peak:Math.max(...r.data.slice(0,500)),stats:r.stats?{irq:r.stats.irqCount,maxISR:r.stats.maxISR,missed:r.stats.missedOverflows}:null}}',mode)
    print(mode,r,flush=True)
   except Exception as exc:errors.append(str(exc));print('ERROR',mode,str(exc)[:800],flush=True)
  print('page_errors',errors)
  await browser.close()
  if errors:raise Exception('Browser smoke-test failed')
asyncio.run(main())
