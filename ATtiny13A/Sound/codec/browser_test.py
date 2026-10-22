#!/usr/bin/env python3
"""Headless Chromium smoke tests for offline player and real HEX verifier."""
from pathlib import Path
import asyncio,json,threading
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from functools import partial
from playwright.async_api import async_playwright
PAGE=Path(__file__).resolve().parent/'index.html'
async def test():
 server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(PAGE.parent)))
 threading.Thread(target=server.serve_forever,daemon=True).start()
 async with async_playwright() as pw:
  b=await pw.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required','--use-fake-ui-for-media-stream'])
  p=await b.new_page(viewport={'width':390,'height':844})
  errors=[];p.on('pageerror',lambda exc:errors.append(str(exc)))
  await p.set_content(PAGE.read_text(),wait_until='load');await p.wait_for_timeout(450)
  assert not errors,errors
  results=[]
  for voice in ['chego','otvechaesh','vinni']:
   await p.select_option('#clip',voice)
   for mode in ['original','old','lpx3','hq']:
    await p.select_option('#variant',mode)
    assert await p.locator('#stoi').inner_text()!='—'
    await p.click('#play');await p.wait_for_timeout(75)
    status=await p.locator('#status').inner_text()
    assert 'Ошибка' not in status,(voice,mode,status)
    await p.click('#stop')
   await p.select_option('#variant','hq')
   await p.click('#verify')
   await p.wait_for_function("() => !document.getElementById('verify').disabled",timeout=120000)
   info=await p.locator('#verifyStats').inner_text()
   assert 'Расхождения с проверенным WAV: 0' in info,(voice,info)
   assert 'Пропуски Timer0: 0' in info,(voice,info)
   results.append((voice,info))
  await b.close();print('Browser: all 12 playback choices OK; AVR HEX verification for all voices OK')
  for name,stat in results:print(name,stat.replace('\n','; '))
  print('JavaScript errors',errors)
  server.shutdown()
if __name__=='__main__':asyncio.run(test())
