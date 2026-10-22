from pathlib import Path
import json, time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
 page=b.new_page(viewport={'width':430,'height':900},device_scale_factor=1)
 js_errors=[];logs=[]
 page.on('pageerror',lambda err: js_errors.append(str(err)))
 page.on('console',lambda obj:logs.append(obj.text) if obj.type=='error' else None)
 page.set_content((ROOT/'index.html').read_text(),wait_until='load')
 print('loaded',page.title(),'buttons',page.locator('button.play').count(),'verify',page.locator('button.verify').count())
 assert page.locator('button.play').count()==9
 for name in ('xtuj-ntt','ne-otv','vinni'):
  for variant in ('source','lpc2','avr'):
   key=name+'_'+variant
   page.locator(f'button[data-track="{key}"]').click(timeout=20000)
   page.wait_for_timeout(100)
   state=page.evaluate('ctx?.state')
   sts=page.locator('#status').inner_text()
   print('PLAY',key,state,sts[:76])
   assert state=='running',state
  page.locator('#stop').click()
 for name in ('xtuj-ntt','ne-otv','vinni'):
  page.locator(f'button.verify[data-name="{name}"]').click(timeout=10000)
  page.wait_for_function(f"!document.querySelector('button.verify[data-name=\"{name}\"]').disabled",timeout=90000)
  s=page.locator('#verify-'+name).inner_text()
  print('VERIFY',name,s)
  assert s.startswith('✓'),s
 page.screenshot(path=str(ROOT/'mobile_preview.png'),full_page=True)
 print('JAVASCRIPT ERRORS',js_errors,logs)
 assert not js_errors and not logs
 b.close()
