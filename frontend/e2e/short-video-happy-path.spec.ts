import { expect, test } from '@playwright/test';
import { enterMockWorkspace } from './helpers';

test('mock 模式可提交通用短视频需求并浏览视频 Skill', async ({ page }) => {
  await enterMockWorkspace(page);

  const composer = page.getByPlaceholder(/@一下 AI 员工/);
  await composer.fill('帮我做一条城市漫游短视频');
  await composer.press('Enter');

  await expect(page.getByText('帮我做一条城市漫游短视频')).toBeVisible();
  await expect(page.getByText('无密钥任务已完成')).toBeVisible();

  await page.goto('/market');
  await page.getByRole('button', { name: '视频' }).click();
  await expect(page.getByText('短视频制作')).toBeVisible();
  await expect(page.locator('body')).not.toContainText('\u53cd\u8bc8');
});

// 登录 → 主会话选模式 → 建短视频群 → HITL 全过 → 拿到 mp4。
// 当前等待真实后端长任务环境，普通 PR 保持显式跳过。
test.skip('短视频 happy path 端到端', async ({ page }) => {
  await page.goto('/');

  await page.getByRole('button', { name: /自动模式|Auto/ }).click();

  const composer = page.getByRole('textbox');
  await composer.fill('帮我做一条城市漫游短视频');
  await composer.press('Enter');

  await expect(page.getByText(/脚本审核|脚本审/)).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: /接受|通过/ }).click();

  await expect(page.getByText(/画面|选图/)).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: /接受|通过/ }).click();

  await expect(page.getByText(/终审/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole('button', { name: /回到第/ })).toHaveCount(0);
  await page.getByRole('button', { name: /接受/ }).click();

  await expect(page.getByText(/\.mp4/)).toBeVisible({ timeout: 60_000 });
});
