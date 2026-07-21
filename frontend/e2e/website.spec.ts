import { expect, test } from '@playwright/test';

test('公开产品页无需登录并可进入登录页', async ({ page }) => {
  await page.goto('/website');
  await expect(page.getByRole('heading', { name: /把 AI 组织成团队/ })).toBeVisible();
  await expect(page.getByText('统一任务与事件契约')).toBeVisible();
  await page.getByRole('link', { name: '登录工作台' }).click();
  await expect(page).toHaveURL(/\/login$/);
});
