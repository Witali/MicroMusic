import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
async def main():
  async with async_playwright() as p:
    browser=await p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--autoplay-policy=user-gesture-required'])
    page=await browser.new_page(viewport={'width':390,'height':780})
    errors=[]
    page.on('pageerror',lambda e: errors.append(str(e)))
    content=(Path(__file__).parent/'release/index.html').read_text()
    await page.set_content(content,wait_until='load')
    print('loaded',await page.title())
    for key in ('xtuj-ntt_original','xtuj-ntt_lpx3','xtuj-ntt_keyframe','xtuj-ntt_adaptive','ne-otv_original','ne-otv_lpx3','ne-otv_keyframe','ne-otv_adaptive'):
      await page.locator(f'button[data-play="{key}"]').click()
      await page.wait_for_timeout(150)
      status=await page.locator('#status').inner_text()
      print(key,status[:105])
      assert status.startswith('▶')
    await page.locator('button[data-check="xtuj-ntt"]').click()
    await page.wait_for_function('document.querySelector("#verify-xtuj-ntt").classList.contains("success") || document.querySelector("#verify-xtuj-ntt").classList.contains("error")',timeout=120000)
    print('verify1',await page.locator('#verify-xtuj-ntt').inner_text())
    await page.locator('button[data-check="ne-otv"]').click()
    await page.wait_for_function('document.querySelector("#verify-ne-otv").classList.contains("success") || document.querySelector("#verify-ne-otv").classList.contains("error")',timeout=120000)
    print('verify2',await page.locator('#verify-ne-otv').inner_text())
    await page.screenshot(path=str(Path(__file__).parent/'release/screenshot.png'),full_page=True)
    print('Errors',errors)
    assert not errors
    assert await page.locator('#verify-xtuj-ntt').get_attribute('class')=='verify small success'
    assert await page.locator('#verify-ne-otv').get_attribute('class')=='verify small success'
    await browser.close()
asyncio.run(main())
