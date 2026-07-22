import puppeteer from "puppeteer";

const TEAMS = [
  ["ILi3oBgH", "Chengdu Rongcheng", "chengdu-rongcheng"],
  ["niRb526o", "Chongqing Tonglianglong", "chongqing-tonglianglong"],
  ["zDctmLjH", "Dalian Yingbo", "dalian-yingbo"],
  ["27dl0BzH", "Shandong Taishan", "shandong-taishan"],
  ["EJp81K5A", "Yunnan Yukun", "yunnan-yukun"],
  ["0QkqH4Gf", "Qingdao West Coast", "qingdao-west-coast"],
  ["WSLjVBLN", "Beijing Guoan", "beijing-guoan"],
  ["ncsQGOBL", "Zhejiang Professional", "zhejiang-professional"],
  ["08kX8Xr0", "Shenzhen Xinpengcheng", "shenzhen-xinpengcheng"],
  ["K8GO0Wwb", "Liaoning Tieren", "liaoning-tieren"],
  ["r5AIrq5q", "Shanghai Shenhua", "shanghai-shenhua"],
  ["O88o93rn", "Shanghai Port", "shanghai-port"],
  ["Ywy81Djb", "Henan Songshan Longmen", "henan-songshan-longmen"],
  ["KbZy1iLA", "Qingdao Hainiu", "qingdao-hainiu"],
  ["SfLUTe08", "Wuhan Three Towns", "wuhan-three-towns"],
  ["tCx1gsk2", "Tianjin Jinmen Tiger", "tianjin-jinmen-tiger"],
];

const DATA_DIR = "/home/openclaw/.openclaw/workspace";

async function fetchTeam(browser, teamId, teamName, teamSlug) {
  console.log(`Fetching ${teamName}...`);
  
  const page = await browser.newPage();
  await page.setUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36");
  
  try {
    await page.goto(`https://www.soccerway.com/team/${teamSlug}/${teamId}/`, {
      waitUntil: "networkidle2",
      timeout: 30000
    });
    
    await new Promise(r => setTimeout(r, 2000));
    
    const players = await page.evaluate(() => {
      const result = [];
      const links = document.querySelectorAll("a[href^=\"/player/\"]");
      links.forEach(link => {
        const href = link.getAttribute("href") || "";
        const match = href.match(/\/player\/([^\/]+)\/([a-zA-Z0-9]+)\//);
        if (match) {
          const slug = match[1];
          const id = match[2];
          const name = link.textContent.trim();
          if (name && id) {
            result.push({ id, name, slug });
          }
        }
      });
      return result;
    });
    
    const seen = new Set();
    const unique = players.filter(p => {
      if (seen.has(p.id)) return false;
      seen.add(p.id);
      return true;
    });
    
    console.log(`  Found ${unique.length} players`);
    
    return {
      team: { id: teamId, name: teamName, slug: teamSlug, country: "China", championship: "Super League" },
      coach: { name: "", nationality: "" },
      stadium: "",
      players: unique,
      matches: [],
      last_updated: Date.now() / 1000
    };
  } catch (e) {
    console.log(`  ERROR: ${e.message}`);
    return null;
  } finally {
    await page.close();
  }
}

async function main() {
  const browser = await puppeteer.launch({
    executablePath: "/usr/bin/chromium-browser",
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
  });
  
  const fs = await import("fs");
  const results = [];
  
  for (const [id, name, slug] of TEAMS) {
    const data = await fetchTeam(browser, id, name, slug);
    if (data) {
      const path = `${DATA_DIR}/_live_cache_${id}.json`;
      fs.writeFileSync(path, JSON.stringify(data, null, 2));
      results.push([name, data.players.length]);
    }
    await new Promise(r => setTimeout(r, 500));
  }
  
  await browser.close();
  
  console.log("\n" + "=".repeat(60));
  console.log(`Total: ${results.length}/${TEAMS.length} teams`);
}

main().catch(e => {
  console.error(e);
  process.exit(1);
});
