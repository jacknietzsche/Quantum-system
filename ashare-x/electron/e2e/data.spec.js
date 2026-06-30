import { test, expect } from '@playwright/test'

test.describe('Data Management', () => {
  test('displays stats cards', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(5).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()
    await expect(page.locator('.text-2xl.font-bold').first()).toBeVisible({ timeout: 15000 })
    await expect(page.locator('.text-2xl.font-bold')).toHaveCount(3)
  })

  test('displays data source health section', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(5).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()
    await expect(page.locator('h3').first()).toBeVisible({ timeout: 15000 })
  })

  test('K-line query section is visible', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(5).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()
    await expect(page.locator('h3').nth(1)).toBeVisible({ timeout: 15000 })
  })
})
