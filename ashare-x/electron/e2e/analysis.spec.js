import { test, expect } from '@playwright/test'

test.describe('Analysis', () => {
  test('displays form with default ticker', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(1).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()
    // Default ticker should be 600519
    await expect(page.locator('input').first()).toHaveValue('600519')
  })

  test('shows error for invalid stock code', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(1).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()

    // Enter invalid code
    await page.locator('input').first().fill('invalid')
    await page.locator('button.bg-sky-600').click()
    // Should show validation error (not start analysis)
    await expect(page.locator('.text-rose-400').first()).toBeVisible()
  })

  test('start analysis shows job progress', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(1).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()

    await page.locator('button.bg-sky-600').click()
    // Should show progress bar or button becomes disabled while loading
    await expect(
      page.locator('button.bg-sky-600:disabled').or(page.locator('.h-2.bg-slate-800.rounded-full'))
    ).toBeVisible({ timeout: 10000 })
  })
})
