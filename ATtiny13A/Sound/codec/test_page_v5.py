from playwright.sync_api import sync_playwright
from pathlib import Path
pagefile=Path(__file__).parent/'index.html'
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--allow-file-access-from-files'])
    tab=browser.new_page()
    errors=[]
    tab.on('pageerror',lambda e: errors.append(str(e)))
    tab.set_content(pagefile.read_text(),wait_until='load',timeout=90000)
    print('Title',tab.title(),'modes',tab.locator('button[data-play]').count(),'JS errors',errors)
    for mode in ['firmware','v4','h4','h8','h12','hprofile','reference']:
        val=tab.evaluate('''async mode=>{const d=await decode(mode);return {length:d.data.length,sr:d.sr,irq:d.stats?.irqCount,missed:d.stats?.missedOverflows}}''',mode)
        print(mode,val,'errors',errors,flush=True)
    tab.screenshot(path=str(pagefile.parent/'screenshot_v5.png'),full_page=True)
    assert not errors
    browser.close()
