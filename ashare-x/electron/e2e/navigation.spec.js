import { test, expect } from '@playwright/test'

test.describe('Navigation', () => {
  test('all 8 nav items are visible and clickable', async ({ page }) => {
    await page.goto('/')
    // Wait for sidebar to load
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 })

    await expect(page.locator('.nav-item')).toHaveCount(8)
    for (let i = 0; i < 8; i++) {
      await expect(page.locator('.nav-item').nth(i)).toBeVisible()
    }
  })

  test('clicking nav items switches pages', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 })

    // Navigate to screening (index 2)
    await page.locator('.nav-item').nth(2).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()

    // Navigate to backtest (index 3)
    await page.locator('.nav-item').nth(3).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()

    // Navigate to settings (index 7)
    await page.locator('.nav-item').nth(7).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()

    // Back to dashboard (index 0)
    await page.locator('.nav-item').nth(0).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()
  })
})
