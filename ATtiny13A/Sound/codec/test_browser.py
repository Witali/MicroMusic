import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
P=Path(__file__).resolve().parent
async def main():
 async with async_playwright() as p:
  b=await p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
  page=await b.new_page(viewport={'width':1100,'height':840})
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  await page.set_content((P/'index.html').read_text(),wait_until='load',timeout=30000)
  print('title:',await page.title(), 'buttons',await page.locator('button[data-play]').count(),flush=True)
  await page.screenshot(path=str(P/'screenshot.png'),full_page=True)
  await page.evaluate('async () => {audioCtx=new AudioContext(); await audioCtx.resume()}')
  for mode in ['firmware','lpc1','lpc2','reference','full']:
   try:
    r=await page.evaluate('async (mode)=>{const r=await decode(mode); let max=0;for (let i=0;i<r.data.length;i++) max=Math.max(max,Math.abs(r.data[i]));return{samples:r.data.length,sampleRate:r.sr,peak:max,stats:r.stats?{irq:r.stats.irqCount,maxISR:r.stats.maxISR,missed:r.stats.missedOverflows}:null}}',mode)
    print('test',mode,r,flush=True)
   except Exception as exc:print('ERROR',mode,str(exc)[:900],flush=True);errors.append(mode+': '+str(exc))
  print('pageerrors',errors)
  await b.close()
asyncio.run(main())
