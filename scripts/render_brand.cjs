// Render the brand SVGs to PNG with Playwright (so fonts and filters match a real browser).
//   PLAYWRIGHT_MODULE=/path/to/playwright node scripts/render_brand.cjs
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs'),
  path = require('node:path');
const root = path.join(__dirname, '..');
/** @type {[string, string, number, number, boolean][]} */
const jobs = [
  // [svg, out png, width, height, transparent background (rounded icons)]
  ['src/naturalvoice/web/icon.svg', 'src/naturalvoice/web/icon-512.png', 512, 512, true],
  ['src/naturalvoice/web/icon.svg', 'src/naturalvoice/web/icon-192.png', 192, 192, true],
  ['src/naturalvoice/web/icon.svg', 'src/naturalvoice/web/apple-touch-icon.png', 180, 180, false],
  ['src/naturalvoice/web/icon.svg', 'src/naturalvoice/web/favicon-32.png', 32, 32, true],
  ['src/naturalvoice/web/icon-maskable.svg', 'src/naturalvoice/web/icon-maskable-512.png', 512, 512, false],
  ['docs/assets/icon-macos.svg', 'docs/assets/icon-1024.png', 1024, 1024, true],
  ['docs/assets/banner.svg', 'docs/assets/banner.png', 1280, 640, false],
];
(async () => {
  const browser = await chromium.launch();
  for (const [svg, out, w, h, transparent] of jobs) {
    const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    const markup = fs.readFileSync(path.join(root, svg), 'utf8');
    await page.setContent(
      `<style>html,body{margin:0;background:${transparent ? 'transparent' : '#0b1310'}}svg{display:block;width:${w}px;height:${h}px}</style>${markup}`,
    );
    await page.screenshot({
      path: path.join(root, out),
      omitBackground: transparent,
      clip: { x: 0, y: 0, width: w, height: h },
    });
    console.log('wrote', out);
    await page.close();
  }
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
