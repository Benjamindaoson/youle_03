import { test, expect } from '@playwright/test';
import { enterMockWorkspace } from './helpers';

/**
 * WS 加固:断线重连 / 事件去重 / 跨 tab 切换持久化
 * 这是 Sprint 6 联调上线 acceptance 的一部分(铁律稳定性)。
 */
test.describe('WebSocket 健壮性', () => {
  test('显式 mock 模式不会启动真实 SSE 或显示断线错误', async ({ page }) => {
    await enterMockWorkspace(page);

    // 模拟 tab 切换；mock 模式不应误连真实服务。
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
    await page.waitForTimeout(500);
    await expect(page.getByText(/连接已断开|重新连接中|实时连接失败/)).not.toBeVisible();
  });
});
