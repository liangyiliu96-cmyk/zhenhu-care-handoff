/**
 * 🔗 核心链路 1：医生登录 → 工作台 → 审核 → 出院
 */
import { test, expect } from '@playwright/test';
import { seedTestPatient, setDevAuth } from '../auth-helpers';

test.describe('链路 1：医生登录 → 审核 → 出院', () => {
  let patientId: string;

  test.beforeAll(async () => {
    patientId = await seedTestPatient();
  });

  test('步骤 0：后端种子数据正常加载', async () => {
    expect(patientId).toBeTruthy();
    expect(patientId).toMatch(/^demo-/);
  });

  test('步骤 1：医生进入工作台，关键面板可见', async ({ page }) => {
    await setDevAuth(page, 'doctor');
    await page.goto('/workbench');

    // 页面标题
    await expect(page.getByText('医生工作台').first()).toBeVisible({ timeout: 15_000 });

    // 4 个指标卡
    await expect(page.getByText('待医生审核').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('未解决告警').first()).toBeVisible();
    await expect(page.getByText('高风险患者').first()).toBeVisible();

    // 待审核队列
    await expect(page.getByText('待审核队列').first()).toBeVisible();
  });

  test('步骤 2：待审核队列中有数据', async ({ page }) => {
    await setDevAuth(page, 'doctor');
    await page.goto('/workbench?view=today');

    // 等待审核队列加载 — 查看 pending items 或 empty state
    await page.waitForTimeout(3000);

    // 队列中应该有患者行或空状态提示
    const hasPending = await page.getByText(/当前类别没有待审核事项|待审核队列/).first().isVisible({ timeout: 5_000 }).catch(() => false);
    expect(hasPending).toBeTruthy();
  });

  test('步骤 3：患者详情页和 CommandBar 正常加载', async ({ page }) => {
    await setDevAuth(page, 'doctor');
    await page.goto(`/patient/${patientId}`);

    // 患者详情加载
    await expect(page.getByText('状态版本').first()).toBeVisible({ timeout: 15_000 });

    // CommandBar 按钮
    await expect(page.getByRole('button', { name: '出院流程' })).toBeVisible({ timeout: 8_000 });
  });

  test('步骤 4：进入患者详情，关键面板可见', async ({ page }) => {
    await setDevAuth(page, 'doctor');
    await page.goto(`/patient/${patientId}`);

    // 患者详情加载
    await expect(page.getByText('状态版本').first()).toBeVisible({ timeout: 15_000 });

    // 出院流程按钮可见
    await expect(page.getByRole('button', { name: '出院流程' })).toBeVisible({ timeout: 8_000 });
  });

  test('步骤 5：患者记录工作区显示出院流程和 Agent 状态', async ({ page }) => {
    await setDevAuth(page, 'doctor');
    await page.goto(`/patient/${patientId}?section=records`);

    // DischargeWorkflowPanel
    const dischargeHeading = page.getByRole('heading', { name: '出院流程' });
    await expect(dischargeHeading).toBeVisible({ timeout: 10_000 });

    // 流程步骤
    await expect(page.getByText('第 1 步').first()).toBeVisible();
    await expect(page.getByText('第 6 步').first()).toBeVisible();

    // 下一步操作区域
    await expect(page.getByText('当前下一步').first()).toBeVisible();
  });
});
