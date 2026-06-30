import { test, expect } from '@playwright/test'

test.describe('Trading Plan', () => {
  test('displays title and action buttons', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(4).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()
    await expect(page.locator('button.bg-sky-600')).toBeVisible()
  })

  test('displays history section', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(4).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()
    await expect(page.locator('h3').first()).toBeVisible({ timeout: 15000 })
  })

  test('rebalance button is visible', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(4).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()
    await expect(page.locator('button.bg-slate-700').first()).toBeVisible()
  })
})
