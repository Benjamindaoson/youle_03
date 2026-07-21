import { expect, test } from '@playwright/test';

// Sprint 5 §4.5 末条 acceptance:
//   登录 → 主会话选模式 → 建反诈视频群 → HITL 全过 → 拿到 mp4
//
// 当前为骨架,等待后端 mock 全部通路打通后启用真实断言。
// 现阶段只验三栏布局 + 模式 chip 渲染。
test.skip('反诈视频 happy path 端到端', async ({ page }) => {
  await page.goto('/');

  // 1) 选 Auto 模式开始
  await page.getByRole('button', { name: /自动模式|Auto/ }).click();

  // 2) 用户在主会话表达"做一条反诈视频" → 触发 Skill 匹配 → 建群
  const composer = page.getByRole('textbox');
  await composer.fill('帮我做一条针对老人的反诈视频');
  await composer.press('Enter');

  // 3) 期望被提名的 skill 是 anti_fraud_video,弹出脚本审核(HITL gate 1)
  await expect(page.getByText(/脚本审核|脚本审/)).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: /接受|通过/ }).click();

  // 4) 画面审核(HITL gate 2)
  await expect(page.getByText(/画面|选图/)).toBeVisible({ timeout: 30_000 });
  await page.getByRole('button', { name: /接受|通过/ }).click();

  // 5) 终审(HITL gate 3)— V1 终审仅 [接受][微调][取消],无回滚按钮
  await expect(page.getByText(/终审/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole('button', { name: /回到第/ })).toHaveCount(0);
  await page.getByRole('button', { name: /接受/ }).click();

  // 6) 拿到 mp4 reference
  await expect(page.getByText(/\.mp4/)).toBeVisible({ timeout: 60_000 });
});
