import { test, expect } from '@playwright/test'

test.describe('Full User Journey', () => {
  test('navigate through all pages sequentially', async ({ page }) => {
    await page.goto('/')

    // 1. Dashboard
    await expect(page.locator('h2.text-xl').first()).toBeVisible({ timeout: 15000 })

    // 2. Analysis
    await page.locator('.nav-item').nth(1).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()

    // 3. Screening
    await page.locator('.nav-item').nth(2).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()

    // 4. Backtest
    await page.locator('.nav-item').nth(3).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()

    // 5. Trading Plan
    await page.locator('.nav-item').nth(4).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()

    // 6. Data
    await page.locator('.nav-item').nth(5).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()

    // 7. Reports
    await page.locator('.nav-item').nth(6).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()

    // 8. Settings
    await page.locator('.nav-item').nth(7).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()
  })

  test('full screening flow', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(2).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()

    // Run screening
    await page.locator('button.bg-sky-600').click()
    // Should show results table or message
    await expect(page.locator('table').or(page.locator('.text-amber-200'))).toBeVisible({ timeout: 30000 })
  })

  test('full data query flow', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(5).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()

    // Stats should load
    await expect(page.locator('.text-2xl.font-bold').first()).toBeVisible({ timeout: 15000 })

    // Query K-line
    await page.locator('button.bg-slate-700').first().click()
    // Should show kline data table or empty message
    await expect(page.locator('th').first()).toBeVisible({ timeout: 30000 })
  })
})
