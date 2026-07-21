import { expect, type Page } from '@playwright/test';

export async function mockLogin(page: Page): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('手机号').fill('13800138000');
  await page.getByRole('button', { name: '获取验证码' }).click();
  await page.getByLabel(/验证码已发送/).fill('123456');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
}

export async function enterMockWorkspace(page: Page): Promise<void> {
  await mockLogin(page);
  await expect(page.getByRole('button', { name: /自动模式 Auto/ })).toBeVisible({
    timeout: 10_000,
  });
  await page.getByRole('button', { name: /自动模式 Auto/ }).click();
  await expect(page).toHaveURL(/\/chat\/main$/);
}
