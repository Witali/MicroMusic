from playwright.sync_api import sync_playwright
from pathlib import Path
html=Path('/mnt/data/MicroMusic_PIC16F1503/web/player.html').read_text()
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
 page=browser.new_page(viewport={'width':1180,'height':880})
 errs=[]
 page.on('pageerror',lambda e: errs.append(str(e)))
 page.set_content(html,wait_until="load")
 assert page.locator('#tabMusic').count()==1
 page.click('#playMusic')
 page.wait_for_function("document.getElementById('samplesCount').innerText !== '0'",timeout=30000)
 print('MUSIC',page.locator('#status').inner_text())
 assert 'note-off' in page.locator('#status').inner_text()
 page.click('#tabCPU')
 page.click('#runCpu')
 page.wait_for_function("document.getElementById('runCpu').disabled===false && document.getElementById('status').innerText.includes('PIC HEX:')",timeout=30000)
 print('CPU',page.locator('#status').inner_text())
 print('ERR',errs)
 page.screenshot(path='/mnt/data/MicroMusic_PIC16F1503/reports/player_screenshot.png',full_page=True)
 assert not errs,errs
 browser.close()
