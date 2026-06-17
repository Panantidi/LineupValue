from playwright.sync_api import sync_playwright
import re
import json

teams = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    try:
        print('Loading Japan J1 League standings...')
        page.goto('https://us.soccerway.com/japan/j1-league/standings/', timeout=180000)
        page.wait_for_timeout(30000)
        
        links = page.query_selector_all('a')
        print(f'Found {len(links)} links')
        
        for link in links:
            href = link.get_attribute('href') or ''
            text = (link.text_content() or '').strip()
            # Match team links: /team/slug/ID/
            match = re.search(r'/team/([^/]+)/([A-Za-z0-9]{8})/?$', href)
            if match and text and len(text) > 2 and len(text) < 30:
                slug = match.group(1)
                team_id = match.group(2)
                teams.append({'id': team_id, 'name': text, 'slug': slug})
        
        seen = set()
        unique = []
        for t in teams:
            if t['id'] not in seen:
                seen.add(t['id'])
                unique.append(t)
        
        print(f'Found {len(unique)} unique teams:')
        for t in unique[:25]:
            print(f'{t["name"]}: {t["id"]} / {t["slug"]}')
        
        if unique:
            with open('/home/openclaw/FormAlert/leagues_data.json', 'r') as f:
                data = json.load(f)
            if 'Japan' not in data:
                data['Japan'] = {}
            data['Japan']['J1 League'] = unique[:25]
            with open('/home/openclaw/FormAlert/leagues_data.json', 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f'Saved {len(unique[:25])} teams to leagues_data.json')
    finally:
        browser.close()