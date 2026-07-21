import { expect, test } from '@playwright/test';

// Sprint 5 acceptance:首次进入 → 总裁助理/HR/财务经理依次入群 + 模式选择卡片
test('首次进入显示三个角色入群 + 三模式选择', async ({ page }) => {
  await page.goto('/');

  // 三个角色介绍至少出现总裁助理
  await expect(page.getByText(/总裁助理/)).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/HR/)).toBeVisible();
  await expect(page.getByText(/财务经理/)).toBeVisible();

  // 三种模式选择卡片(铁律 17:同群切换)
  await expect(page.getByRole('button', { name: /讨论模式|Plan/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /询问模式|Ask/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /自动模式|Auto/ })).toBeVisible();
});
