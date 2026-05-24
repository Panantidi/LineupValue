#!/usr/bin/env python3
"""Debug: check lf__sidesBox structure"""
import asyncio, re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def main():
    url = 'https://www.soccerway.com/match/espanyol-QFfPdh1J/osasuna-ETdxjU8a/summary/lineups/?mid=YFVo6qXh'
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            '--no-sandbox', '--disable-setuid-sandbox',
            '--disable-blink-features=AutomationControlled'
        ])
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080}, locale='en-US'
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = await context.new_page()
        await page.goto(url, wait_until='load', timeout=30000)
        await page.wait_for_timeout(4000)
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 500)")
            await page.wait_for_timeout(500)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(2000)
        
        html = await page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check lf__sidesBox structure
        boxes = soup.find_all('div', class_='lf__sidesBox')
        print(f"lf__sidesBox count: {len(boxes)}")
        for i, box in enumerate(boxes):
            left = box.select('[data-testid="wcl-lineupsParticipantGeneral-left"]')
            right = box.select('[data-testid="wcl-lineupsParticipantGeneral-right"]')
            left_names = []
            right_names = []
            for p_el in left:
                b = p_el.select_one('span[class*="wcl-bold"]')
                if b: left_names.append(b.get_text(strip=True))
            for p_el in right:
                b = p_el.select_one('span[class*="wcl-bold"]')
                if b: right_names.append(b.get_text(strip=True))
            print(f"\nBox {i}: left={len(left)} right={len(right)}")
            print(f"  Left names: {left_names}")
            print(f"  Right names: {right_names}")
        
        # Check sourceline availability
        el = soup.select_one('[data-testid="wcl-lineupsParticipantGeneral-left"]')
        print(f"\nsourceline test: {el.sourceline if el else 'no el'}")
        print(f"sourcepos test: {el.sourcepos if el else 'no el'}")
        
        await browser.close()

asyncio.run(main())
