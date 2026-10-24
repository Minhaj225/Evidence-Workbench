import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('upload, ingest, answer, inspect source, abstain, evaluate and delete', async ({ page, request }) => {
  const consoleErrors: string[] = [];
  page.on('pageerror', error => consoleErrors.push(error.message));
  await page.goto('/documents');
  await expect(page.getByRole('heading', { name: 'Documents', exact: true })).toBeVisible();
  await page.getByLabel('Choose documents').setInputFiles({name: 'browser-fixture.pdf', mimeType: 'application/pdf', buffer: readFileSync('../backend/tests/fixtures/source.pdf')});
  const row = page.getByRole('row').filter({hasText: 'browser-fixture.pdf'});
  await expect(row.locator('.status')).toHaveText('ready', { timeout: 30000 });
  await page.getByRole('link', { name: 'Ask a question', exact: true }).click();
  await page.getByLabel('What would you like to know?').fill('What are the core functions?');
  await page.getByRole('button', { name: 'Ask question', exact: true }).click();
  const marker = page.getByRole('button', {name: 'Open source S1'});
  await expect(marker).toBeVisible();
  await marker.click();
  const drawer = page.getByRole('dialog');
  await expect(drawer.getByRole('heading')).toHaveText('browser-fixture.pdf');
  await expect(drawer.getByText('Page 1', {exact: true})).toBeVisible();
  const image = drawer.getByRole('img');
  await expect(image).toBeVisible();
  await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
  await page.screenshot({path: '../docs/screenshots/citation-fixture.png', fullPage: true});
  for (let i = 0; i < 6; i++) {
    await page.keyboard.press('Tab');
    await expect.poll(() => drawer.evaluate(d => d.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press('Escape');
  await expect(drawer).not.toBeVisible();
  await expect(marker).toBeFocused();
  await page.getByLabel('What would you like to know?').fill('Who is the president of Mars?');
  await page.getByRole('button', {name:'Ask question', exact:true}).click();
  await expect(page.getByText('Insufficient evidence', {exact:true})).toBeVisible();
  await page.getByRole('link', {name:'Evaluation', exact:true}).click();
  await expect(page.getByText('Synthetic browser fixture', {exact:false})).toBeVisible();
  await expect(page.getByText('Baseline HitRate@5', {exact:true})).toBeVisible();
  await page.getByText('Fixture question 1', {exact:true}).first().click();
  await expect(page.locator('details[open]').getByText('Fixture reference.', {exact:true})).toBeVisible();
  // A missing corpus must be a visible error, never example quality scores.
  await page.getByRole('button', {name:'Run benchmark'}).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await page.getByRole('link', {name:'Documents', exact:true}).click();
  page.once('dialog', d => d.accept());
  await page.getByRole('button', {name:'Delete browser-fixture.pdf'}).click();
  await expect(row).toHaveCount(0);
  const docs = await (await request.get('/api/documents')).json();
  expect(docs).toHaveLength(0);
  expect(consoleErrors).toEqual([]);
});

test('mobile layout stays within viewport', async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await page.goto('/documents');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await expect(page.getByLabel('Choose documents')).toBeVisible();
});
