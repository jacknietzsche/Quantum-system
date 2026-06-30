import { test, expect } from '@playwright/test'

test.describe('Reports', () => {
  test('displays title and filter input', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(6).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()
    await expect(page.locator('input').first()).toBeVisible()
  })

  test('displays report list or empty state', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(6).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()
    // Wait for either table or empty state text
    await expect(
      page.locator('table').or(page.locator('.text-center'))
    ).toBeVisible({ timeout: 15000 })
  })
})
