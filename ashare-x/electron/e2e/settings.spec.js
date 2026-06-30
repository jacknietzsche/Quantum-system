import { test, expect } from '@playwright/test'

test.describe('Settings', () => {
  test('displays settings sections', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(7).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()
    await expect(page.locator('h3').first()).toBeVisible({ timeout: 15000 })
    await expect(page.locator('h3').nth(1)).toBeVisible()
  })

  test('displays LLM provider dropdown', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(7).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()
    // Check select element is visible and has options
    await expect(page.locator('select').first()).toBeVisible({ timeout: 15000 })
    const optionCount = await page.locator('select option').count()
    expect(optionCount).toBeGreaterThan(0)
  })

  test('save button is visible', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(7).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()
    await expect(page.locator('button.bg-sky-600')).toBeVisible({ timeout: 15000 })
  })
})
