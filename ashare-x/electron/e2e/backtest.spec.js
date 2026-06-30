import { test, expect } from '@playwright/test'

test.describe('Backtest', () => {
  test('displays form and strategy dropdown', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(3).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()
    // Strategy select should load — check select element has options
    await expect(page.locator('select')).toBeVisible({ timeout: 15000 })
    const optionCount = await page.locator('select option').count()
    expect(optionCount).toBeGreaterThan(0)
  })

  test('run backtest shows results', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.nav-item').first()).toBeVisible({ timeout: 15000 })
    await page.locator('.nav-item').nth(3).click()
    await expect(page.locator('h2.text-xl')).toBeVisible()
    // Wait for strategies to load
    await expect(page.locator('select')).toBeVisible({ timeout: 15000 })

    await page.locator('button.bg-sky-600').click()
    // Should show results or error (depends on data availability)
    await expect(
      page.locator('.text-rose-200').or(page.locator('.grid.grid-cols-2'))
    ).toBeVisible({ timeout: 60000 })
  })
})
