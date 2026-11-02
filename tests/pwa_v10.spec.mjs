// Browser regression tests (WebKit = Safari engine; Chromium mobile = Android/iPhone-size viewport).
// Run with: npm install --no-save @playwright/test && npx playwright install chromium webkit && npx playwright test tests/pwa_v10.spec.mjs
import { test, expect, devices } from '@playwright/test';

const mobiles = [
  ['Chromium mobile', { ...devices['iPhone 13'], defaultBrowserType: 'chromium' }],
  ['Safari WebKit mobile', { ...devices['iPhone 13'], defaultBrowserType: 'webkit' }],
];

for (const [name, device] of mobiles) {
  test.describe(name, () => {
    test.use({ ...device, baseURL: 'http://127.0.0.1:8765', serviceWorkers: 'allow' });
    test('local edition, game picker and edit-dialog scroll', async ({ page }) => {
      await page.goto('/index.html');
      await page.locator('[data-first-mode="local"]').click();
      await page.locator('#addGameButton').click();
      await page.locator('#titleInput').fill('v10 Smoke Test');
      await page.locator('#gameTypeInput').selectOption('base');
      await page.locator('#editionLanguageInput').fill('Deutsch');
      await page.locator('#editionYearInput').fill('2026');
      await page.locator('#gameForm button[type="submit"]').click();
      await expect(page.locator('#gameDialog')).not.toBeVisible();
      await expect(page.locator('#gameList')).toContainText('v10 Smoke Test');
      await page.locator('#gamePickerOpen').click();
      await page.locator('#pickerChoose').click();
      await expect(page.locator('#pickerResult')).toContainText('v10 Smoke Test');
      await page.locator('#gamePickerClose').click();
      await page.locator('#gameList .game-card button').first().click();
      await expect(page.locator('#gameDetailDialog')).toBeVisible();
      await page.locator('#detailEditButton').click();
      await expect(page.locator('#gameDialog')).toBeVisible();
      await expect(page.locator('#editionLanguageInput')).toHaveValue('Deutsch');
      expect(await page.locator('#gameForm').evaluate(el=>el.scrollTop)).toBe(0);
    });
    test('old UI controls retained; scanner has manual EAN input', async ({ page }) => {
      await page.goto('/index.html');
      await expect(page.locator('#initialBggOnlyInput')).toHaveCount(1);
      await expect(page.locator('#openScannerButton')).toHaveCount(1);
      await expect(page.locator('#barcodeManual')).toHaveCount(1);
      await expect(page.locator('#gamePickerDialog')).toHaveCount(1);
    });
    test('PWA caches app shell for offline reload', async ({ page, context }) => {
      await page.goto('/index.html');
      await page.evaluate(async()=>await navigator.serviceWorker.ready);
      await context.setOffline(true);
      await page.reload();
      await expect(page.locator('#collectionHeading')).toBeVisible();
      await context.setOffline(false);
    });
  });
}
