from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
 page=browser.new_page(viewport={'width':400,'height':850},device_scale_factor=1)
 errors=[]
 page.on('pageerror', lambda e: errors.append(str(e)))
 page.set_content((ROOT/'index.html').read_text(encoding='utf8'),wait_until='load',timeout=20000)
 for voice in ('chego','otvechaesh','vinni'):
  page.select_option('#voice',voice)
  for mode in ('old','original','new','lpx3'):
   page.select_option('#codec',mode)
   page.click('#play')
   page.wait_for_timeout(150)
   assert 'Ошибка' not in page.locator('#status').inner_text(),(voice,mode,page.locator('#status').inner_text())
  page.select_option('#codec','new')
  page.click('#verify')
  page.wait_for_function("document.querySelector('#verifyStatus').innerText.includes('Проверка пройдена') || document.querySelector('#verifyStatus').innerText.includes('Ошибка')",timeout=120000)
  status=page.locator('#verifyStatus').inner_text()
  print(voice,status)
  assert 'Проверка пройдена' in status,status
 page.select_option('#voice','vinni')
 page.select_option('#codec','new')
 page.screenshot(path=str(ROOT/'mobile_preview.png'),full_page=True)
 print('errors:',errors)
 assert not errors
 browser.close()
