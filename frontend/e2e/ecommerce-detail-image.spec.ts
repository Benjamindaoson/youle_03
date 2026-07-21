import { test, expect } from '@playwright/test';
import { enterMockWorkspace } from './helpers';

/**
 * 电商详情图 hero 任务 E2E(Sprint 6 acceptance)
 *
 * 流程:
 * 浏览器层验证无密钥模式的关键交互；完整 Redis/AgentResult/SSE 链路由
 * backend/tests/integration/test_no_key_platform_e2e.py 覆盖。
 */
test.describe('电商详情图 happy path', () => {
  test.use({ storageState: undefined });

  test('提交电商详情图需求并浏览匹配 Skill', async ({ page }) => {
    await enterMockWorkspace(page);

    const composer = page.getByPlaceholder(/@一下 AI 员工/);
    await composer.fill('做一套保温杯的电商详情图,极简白底,6 张');
    await composer.press('Enter');
    await expect(page.getByText('做一套保温杯的电商详情图,极简白底,6 张')).toBeVisible();
    await expect(page.getByText('无密钥任务已完成')).toBeVisible();
    await expect(page.getByText(/mock AgentResult 已通过统一 UserEvent/)).toBeVisible();

    await page.goto('/market');
    await expect(page.getByRole('heading', { name: '技能市场' })).toBeVisible();
    await page.getByRole('button', { name: '图像' }).click();
    await expect(page.getByText('电商详情图制作')).toBeVisible();
    await expect(page.getByRole('button', { name: /已启用|安装并启用/ })).toBeVisible();
  });
});
