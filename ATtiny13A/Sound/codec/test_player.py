from playwright.sync_api import sync_playwright
from pathlib import Path
p=Path(__file__).parent/'MicroMusic_LPC2_Lite_Emulator.html'
with sync_playwright() as m:
 browser=m.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--allow-file-access-from-files','--autoplay-policy=no-user-gesture-required'])
 page=browser.new_page(viewport={'width':1100,'height':900})
 errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.set_content(p.read_text(),wait_until='load',timeout=60000)
 print('title',page.title(),'buttons',page.locator('[data-play]').count())
 for id in ['original','lpc2','v5','glide','mixed']:
  a=page.evaluate('''async id=>{const x=await decodeTrack(id);return {length:x.samples.length,sr:x.sr,irq:x.stats?.irq,missed:x.stats?.missed,maxISR:x.stats?.maxISR,peak:Math.max(...x.samples)}}''',id)
  print(id,a,flush=True)
  assert (a['length'] in [22200,22272,23680]),a
  assert (a['missed'] is None or a['missed']==0),a
 assert not errors,errors
 page.locator('[data-play="glide"]').click()
 print('play status',page.locator('#status').inner_text())
 page.screenshot(path=str(p.parent/'screenshot.png'),full_page=True)
 print('browser errors',errors)
 browser.close()
