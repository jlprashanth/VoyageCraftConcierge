const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { PNG } = require('pngjs');
const GIFEncoder = require('gif-encoder-2');

async function createGif() {
  const width = 800;
  const height = 500;

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width, height } });

  console.log('Navigating to VoyageCraft Frontend for GIF recording...');
  await page.goto('https://voyagecraft-frontend-1069236132412.us-east1.run.app', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);

  const frames = [];

  async function capture(durationMs, fps = 4) {
    const interval = 1000 / fps;
    const count = Math.floor(durationMs / interval);
    for (let i = 0; i < count; i++) {
      const buf = await page.screenshot({ type: 'png' });
      frames.push(buf);
      await page.waitForTimeout(interval);
    }
  }

  // 1. Initial view & click prompt chip
  await capture(1000);
  const chip = await page.locator('.prompt-chip').first();
  await chip.click();

  // 2. Capture destination search response & A2UI cards
  await capture(7000, 3);

  // 3. Type budget prompt
  await page.fill('#input', 'Calculate budget breakdown for 5 days in Tokyo for 2 travelers');
  await capture(500);
  await page.click('#form button');

  // 4. Capture budget calculation result
  await capture(9000, 3);

  await browser.close();

  console.log(`Captured ${frames.length} frames. Encoding GIF...`);

  const firstPng = PNG.sync.read(frames[0]);
  const encoder = new GIFEncoder(firstPng.width, firstPng.height, 'octree', false);
  encoder.start();
  encoder.setRepeat(0); // 0 = loop forever
  encoder.setDelay(333); // ~3 fps
  encoder.setQuality(10);

  for (let i = 0; i < frames.length; i++) {
    const png = PNG.sync.read(frames[i]);
    encoder.addFrame(png.data);
  }

  encoder.finish();
  const buffer = encoder.out.getData();
  const gifPath = path.join(__dirname, 'demo.gif');
  fs.writeFileSync(gifPath, buffer);
  console.log(`GIF successfully created and saved to demo.gif (${(buffer.length / 1024 / 1024).toFixed(2)} MB)!`);
}

createGif().catch(err => {
  console.error('Error creating GIF:', err);
  process.exit(1);
});
