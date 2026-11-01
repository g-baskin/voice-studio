const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');

async function launch(options) {
  const browser = await chromium.launch(options);
  const close = browser.close.bind(browser);
  browser.close = async () => {
    try {
      if (process.env.NV_SCREENSHOTS) {
        fs.mkdirSync(process.env.NV_SCREENSHOTS, { recursive: true });
        for (const [i, context] of browser.contexts().entries()) {
          for (const [j, page] of context.pages().entries()) {
            if (!page.isClosed()) {
              await page
                .screenshot({
                  path: path.join(process.env.NV_SCREENSHOTS, `final-${i}-${j}.png`),
                  fullPage: true,
                  timeout: 5000,
                })
                .catch(() => {});
            }
          }
        }
      }
    } finally {
      await close();
    }
  };
  return browser;
}
module.exports = { launch };
