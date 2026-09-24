const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

async function recordDemo() {
  const outputDir = path.join(__dirname, 'demo_recordings');
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  const browser = await chromium.launch({
    headless: true,
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: {
      dir: outputDir,
      size: { width: 1280, height: 720 }
    }
  });

  const page = await context.newPage();
  console.log('Navigating to VoyageCraft Frontend...');
  await page.goto('https://voyagecraft-frontend-1069236132412.us-east1.run.app', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  // 1. First prompt: Click example prompt chip for destination search
  console.log('Clicking example prompt chip: Search luxury beach destinations');
  const chip = await page.locator('.prompt-chip').first();
  await chip.click();

  // Wait for response and A2UI cards to render
  console.log('Waiting for destination search response...');
  await page.waitForTimeout(10000);

  // 2. Second, richer prompt: Budget calculation tool call & breakdown
  console.log('Sending second prompt: Calculate budget breakdown for 5 days in Tokyo for 2 travelers');
  await page.fill('#input', 'Calculate budget breakdown for 5 days in Tokyo for 2 travelers');
  await page.click('#form button');

  // Wait for budget tool calculation response
  console.log('Waiting for budget tool calculation response...');
  await page.waitForTimeout(12000);

  console.log('Closing browser and saving video recording...');
  const videoPath = await page.video().path();
  await context.close();
  await browser.close();

  const targetPath = path.join(__dirname, 'voyagecraft_demo.webm');
  if (fs.existsSync(videoPath)) {
    fs.renameSync(videoPath, targetPath);
    console.log(`Demo video successfully recorded and saved to: ${targetPath}`);
  }
}

recordDemo().catch(err => {
  console.error('Error recording demo:', err);
  process.exit(1);
});
