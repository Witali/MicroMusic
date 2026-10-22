from playwright.sync_api import sync_playwright
from pathlib import Path
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
 page=browser.new_page(viewport={'width':430,'height':780})
 errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.set_content(Path(__file__).resolve().parent.joinpath('index.html').read_text(),wait_until='load')
 assert page.locator('#flash').inner_text()=='929'
 page.locator('#play').click()
 page.wait_for_timeout(750)
 print('play:',page.locator('#status').inner_text())
 page.locator('#stop').click()
 page.locator('#clip').select_option('vinni')
 assert page.locator('#flash').inner_text()=='989'
 page.locator('#verify').click()
 page.wait_for_function("!document.querySelector('#verify').disabled",timeout=120000)
 print('verify:',page.locator('#status').inner_text())
 assert '0 расхождений' in page.locator('#status').inner_text()
 assert '0'==str(page.evaluate('0'))
 assert not errors,errors
 page.screenshot(path=str(Path(__file__).parent/'mobile_preview.png'),full_page=True)
 browser.close()
