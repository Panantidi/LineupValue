import asyncio
import httpx

class FetchTester:
    async def run(self):
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = await client.get('https://www.soccerway.com/teams/france/ligue-1/')
            print(f'\n✅ Fetched {len(r.text)} chars in {r.elapsed.total_seconds():.2f}s')
            print(f'➡️ Status: {r.status_code}')
            if r.status_code == 200:
                print('→ First 100 chars:')
                print(repr(r.text[:100]))

if __name__ == '__main__':
    asyncio.run(FetchTester().run())