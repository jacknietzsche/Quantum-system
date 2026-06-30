import { test, expect } from '@playwright/test'

test.describe('Screening', () => {
  test('displays style selector and run button', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(2).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()
    await expect(page.locator('select')).toBeVisible()
    await expect(page.locator('button.bg-sky-600')).toBeVisible()
  })

  test('run screening displays results table', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(2).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()

    await page.locator('button.bg-sky-600').click()
    // Wait for results table or message
    await expect(page.locator('table').or(page.locator('.text-amber-200'))).toBeVisible({ timeout: 30000 })
  })
})
