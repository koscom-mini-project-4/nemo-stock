/**
 * checkapi.koscom.co.kr 문서 크롤러.
 *
 * 사용법: node koscom_crawler.js <category1> [category2 ...]
 * 카테고리 이름은 사이트 사이드바 텍스트 그대로: 주식-API, 파생-API, 채권-API,
 * "해외-API (license)", 뉴스/공시-API, 기타-API
 *
 * 각 카테고리 > 그룹 > 리프 페이지를 순회하며 본문(.contents)을 추출해
 * OUT_DIR/<category-slug>/<group-slug>/<NN-leaf-slug>.md 로 저장한다.
 * 진행 로그는 stdout + OUT_DIR/_crawl-log.jsonl 에 누적 기록한다(중단되어도 이어 확인 가능).
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const OUT_DIR = path.join(__dirname, '..', 'pages');
fs.mkdirSync(OUT_DIR, { recursive: true });

const LOG_PATH = path.join(OUT_DIR, '_crawl-log.jsonl');

function slugify(name) {
  return name
    .trim()
    .replace(/[\\/:*?"<>|]/g, '-')
    .replace(/\s+/g, ' ')
    .slice(0, 80);
}

function logLine(obj) {
  fs.appendFileSync(LOG_PATH, JSON.stringify(obj) + '\n');
  console.log(JSON.stringify(obj));
}

const CATEGORY_SLUGS = {
  '주식-API': '01-stock-api',
  '파생-API': '02-derivative-api',
  '채권-API': '03-bond-api',
  '해외-API (license)': '04-overseas-api',
  '뉴스/공시-API': '05-news-disclosure-api',
  '기타-API': '06-etc-api',
};

async function main() {
  const targetCategories = process.argv.slice(2);
  if (targetCategories.length === 0) {
    console.error('Usage: node koscom_crawler.js <category> [category...]');
    process.exit(1);
  }

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1600, height: 1400 } });
  await page.goto('https://checkapi.koscom.co.kr/intro/introhome', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(1000);

  let totalOk = 0;
  let totalFail = 0;

  for (const category of targetCategories) {
    const catSlug = CATEGORY_SLUGS[category] || slugify(category);
    logLine({ level: 'category', category });

    try {
      await page.click(`text=${category}`, { force: true, timeout: 8000 });
      await page.waitForTimeout(500);
    } catch (e) {
      logLine({ level: 'error', stage: 'category-expand', category, message: e.message });
      continue;
    }

    // discover groups + leaves for this category (structural, DOM-based, works even if visually collapsed)
    const groups = await page.evaluate((catName) => {
      const headers = Array.from(document.querySelectorAll('.txt_opentype'));
      const header = headers.find((h) => h.textContent.trim() === catName);
      if (!header) return [];
      const outerUl = header.closest('ul.list_opentype');
      if (!outerUl) return [];
      const groupLis = outerUl.querySelectorAll(':scope > ul.list_defaulttype > li');
      const result = [];
      groupLis.forEach((li) => {
        const nameEl = li.querySelector(':scope > .link_sidemenu > .txt_sidemenu');
        const name = nameEl ? nameEl.textContent.trim() : null;
        const leaves = Array.from(li.querySelectorAll(':scope > ul.list_detailidx > li > .txt_detailidx')).map((s) =>
          s.textContent.trim(),
        );
        if (name) result.push({ name, leaves });
      });
      return result;
    }, category);

    for (const group of groups) {
      const groupSlug = slugify(group.name);
      const groupDir = path.join(OUT_DIR, catSlug, groupSlug);
      fs.mkdirSync(groupDir, { recursive: true });

      // expand the group (click its header) so leaf items become clickable/visible
      try {
        await page.click(`text=${group.name}`, { force: true, timeout: 8000 });
        await page.waitForTimeout(350);
      } catch (e) {
        logLine({ level: 'error', stage: 'group-expand', category, group: group.name, message: e.message });
      }

      let idx = 0;
      for (const leafRaw of group.leaves) {
        idx += 1;
        const leaf = leafRaw;
        const fileName = `${String(idx).padStart(2, '0')}-${slugify(leaf)}.md`;
        const filePath = path.join(groupDir, fileName);

        let attempt = 0;
        let ok = false;
        while (attempt < 2 && !ok) {
          attempt += 1;
          try {
            // 같은 이름의 리프가 여러 그룹에 있을 수 있으므로, 이 그룹의 leaf 목록 컨테이너로 범위를 좁혀 클릭한다.
            const clicked = await page.evaluate(
              ({ catName, groupName, leafName }) => {
                const headers = Array.from(document.querySelectorAll('.txt_opentype'));
                const header = headers.find((h) => h.textContent.trim() === catName);
                if (!header) return false;
                const outerUl = header.closest('ul.list_opentype');
                if (!outerUl) return false;
                const groupLis = outerUl.querySelectorAll(':scope > ul.list_defaulttype > li');
                let targetLeafEl = null;
                groupLis.forEach((li) => {
                  const nameEl = li.querySelector(':scope > .link_sidemenu > .txt_sidemenu');
                  if (nameEl && nameEl.textContent.trim() === groupName) {
                    const leafEls = li.querySelectorAll(':scope > ul.list_detailidx > li > .txt_detailidx');
                    leafEls.forEach((el) => {
                      if (el.textContent.trim() === leafName && !targetLeafEl) targetLeafEl = el;
                    });
                  }
                });
                if (targetLeafEl) {
                  targetLeafEl.click();
                  return true;
                }
                return false;
              },
              { catName: category, groupName: group.name, leafName: leaf },
            );

            if (!clicked) throw new Error('leaf element not found for click');

            await page.waitForTimeout(450);
            const content = await page.evaluate(() => document.querySelector('.contents')?.innerText || '');
            const url = page.url();

            if (!content || content.trim().length < 5) {
              throw new Error('empty content extracted');
            }

            const md = `# ${leaf}\n\n- category: ${category}\n- group: ${group.name}\n- url: ${url}\n\n---\n\n${content}\n`;
            fs.writeFileSync(filePath, md, 'utf-8');
            ok = true;
            totalOk += 1;
          } catch (e) {
            if (attempt >= 2) {
              logLine({ level: 'error', stage: 'leaf', category, group: group.name, leaf, message: e.message });
              totalFail += 1;
            } else {
              await page.waitForTimeout(500);
            }
          }
        }
      }
      logLine({ level: 'group-done', category, group: group.name, leafCount: group.leaves.length });
    }
    logLine({ level: 'category-done', category, groupCount: groups.length });
  }

  logLine({ level: 'summary', totalOk, totalFail });
  await browser.close();
}

main().catch((e) => {
  console.error('CRAWLER FAILED:', e);
  process.exit(1);
});
