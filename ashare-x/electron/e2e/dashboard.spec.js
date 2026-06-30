import { test, expect } from '@playwright/test'

test.describe('Dashboard', () => {
  test('loads and displays title', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('h2.text-xl')).toBeVisible({ timeout: 15000 })
  })

  test('displays stat cards after loading', async ({ page }) => {
    await page.goto('/')
    // Wait for loading to finish and stat cards to appear
    await expect(page.locator('.text-2xl.font-bold').first()).toBeVisible({ timeout: 15000 })
    await expect(page.locator('.text-2xl.font-bold')).toHaveCount(4)
  })

  test('shows welcome message', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('h1')).toBeVisible({ timeout: 15000 })
  })
})
