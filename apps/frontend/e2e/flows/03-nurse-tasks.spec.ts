/**
 * 🔗 核心链路 3：护士 → 护理看板 → 查看各面板
 */
import { test, expect } from '@playwright/test';
import { seedTestPatient, setDevAuth } from '../auth-helpers';

test.describe('链路 3：护士 → 护理看板', () => {
  test.beforeAll(async () => {
    await seedTestPatient();
  });

  test('步骤 1：护士进入护理看板，页面标题正确', async ({ page }) => {
    await setDevAuth(page, 'nurse');
    await page.goto('/nurse');

    // 页面标题
    await expect(page.getByText('护理看板').first()).toBeVisible({ timeout: 15_000 });
  });

  test('步骤 2：切换到护理任务标签页', async ({ page }) => {
    await setDevAuth(page, 'nurse');
    await page.goto('/nurse?tab=tasks');

    // AI 优先级建议或任务面板
    await expect(page.getByText(/优先|护理任务|建议/).first()).toBeVisible({ timeout: 10_000 });
  });

  test('步骤 3：查看在院患者目录', async ({ page }) => {
    await setDevAuth(page, 'nurse');
    await page.goto('/nurse?tab=patients');

    // 搜索框可见
    await expect(page.getByPlaceholder(/搜索患者/).first()).toBeVisible({ timeout: 10_000 });
  });

  test('步骤 4：查看交班报告', async ({ page }) => {
    await setDevAuth(page, 'nurse');
    await page.goto('/nurse?tab=shift');

    // 交班报告区域
    await expect(page.getByText(/交班|重点关注|在院汇总/).first()).toBeVisible({ timeout: 10_000 });
  });

  test('步骤 5：查看制度执行', async ({ page }) => {
    await setDevAuth(page, 'nurse');
    await page.goto('/nurse?tab=checklist');

    // 制度执行面板
    await expect(page.getByText(/制度执行|制度要求/).first()).toBeVisible({ timeout: 10_000 });
  });

  test('步骤 6：护士查看患者详情', async ({ page }) => {
    await setDevAuth(page, 'nurse');
    await page.goto('/nurse?tab=patients');

    // 等待患者列表
    await expect(page.getByPlaceholder(/搜索患者/).first()).toBeVisible({ timeout: 10_000 });

    // 点详情按钮（如果列表有患者）
    const detailBtn = page.getByRole('button', { name: '详情' }).first();
    const visible = await detailBtn.isVisible({ timeout: 3_000 }).catch(() => false);
    if (visible) {
      await detailBtn.click();
      await expect(page.getByText('护理患者详情').first()).toBeVisible({ timeout: 5_000 });

      // 关闭抽屉
      await page.getByLabel('关闭患者详情').click();
    }
  });
});
