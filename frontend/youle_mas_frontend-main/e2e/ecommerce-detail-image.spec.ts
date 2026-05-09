import { test, expect } from '@playwright/test';

/**
 * 电商详情图 hero 任务 E2E(Sprint 6 acceptance)
 *
 * 流程:
 *   1. 登录 → 主会话
 *   2. 切到 Auto 模式
 *   3. 用关键词触发 ecommerce_detail_image Skill
 *   4. 等到执行流出现下载/批量生成/拼图 step
 *   5. 验证 [接受] 终审 → 拿到长图
 */
test.describe('电商详情图 happy path', () => {
  test.use({ storageState: undefined });

  test('生成 6 张详情图并拼成长图', async ({ page }) => {
    await page.goto('/');

    // 登录(mock 环境直接跳过;真环境用测试账号)
    if (await page.getByText('登录').isVisible({ timeout: 2000 }).catch(() => false)) {
      await page.getByLabel('手机号').fill('13800000001');
      await page.getByLabel('验证码').fill('123456');
      await page.getByRole('button', { name: '登录' }).click();
    }

    // 主会话默认存在
    await expect(page.getByText('总裁助理')).toBeVisible({ timeout: 10000 });

    // 切 Auto
    await page.getByRole('button', { name: /Auto|🚀/ }).click();
    await expect(page.getByText(/自动模式/)).toBeVisible();

    // 触发 Skill — 一句话下需求
    const composer = page.getByPlaceholder(/输入消息|说点什么/);
    await composer.fill('做一套保温杯的电商详情图,极简白底,6 张');
    await composer.press('Enter');

    // 主编排接收 → 澄清(可能直接进 Auto)→ 看到执行流
    const exec = page.getByTestId('execution-stream');
    await expect(exec).toBeVisible({ timeout: 30000 });

    // 期待 step:image_download / batch_generate / image_concat_long
    await expect(exec.getByText(/批量生成|生成中/)).toBeVisible({ timeout: 60000 });

    // 等长图(primary_artifact)
    const longImage = page.getByTestId('artifact-image');
    await expect(longImage).toBeVisible({ timeout: 180000 });

    // 用户接受
    const acceptBtn = page.getByRole('button', { name: /接受|发布|完成/ });
    if (await acceptBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await acceptBtn.click();
    }

    // 任务完成 chip
    await expect(page.getByText(/任务完成|已交付/)).toBeVisible({ timeout: 30000 });
  });
});
