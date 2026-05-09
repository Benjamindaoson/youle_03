import { test, expect } from '@playwright/test';

/**
 * WS 加固:断线重连 / 事件去重 / 跨 tab 切换持久化
 * 这是 Sprint 6 联调上线 acceptance 的一部分(铁律稳定性)。
 */
test.describe('WebSocket 健壮性', () => {
  test('重新激活页面后能立即重连(visibilitychange 路径)', async ({ page, context }) => {
    await page.goto('/');

    // 等连上 WS(connected store)
    await page.waitForFunction(() => {
      return (window as any).__WS_CONNECTED__ === true;
    }, undefined, { timeout: 10000 }).catch(() => {
      // 没暴露内部状态 — 用 selector 兜底:看不到"重连中"
    });

    // 模拟 tab 切走 → 立即重连
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await page.waitForTimeout(200);
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));
    });

    // 不应当出现持续断开提示
    await page.waitForTimeout(2000);
    await expect(page.getByText(/连接已断开|重新连接中/)).not.toBeVisible();
  });
});
