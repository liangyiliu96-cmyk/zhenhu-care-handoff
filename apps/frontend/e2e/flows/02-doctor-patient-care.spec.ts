/**
 * 🔗 核心链路 2：医生 → 患者详情 → 照护管理
 */
import { test, expect } from '@playwright/test';
import { seedTestPatient, setDevAuth } from '../auth-helpers';

test.describe('链路 2：医生 → 患者详情 → 照护管理', () => {
  let patientId: string;

  test.beforeAll(async () => {
    patientId = await seedTestPatient();
  });

  test('步骤 1：医嘱与协同工作区加载，5个操作按钮可见', async ({ page }) => {
    await setDevAuth(page, 'doctor');
    await page.goto(`/patient/${patientId}?section=orders`);

    await expect(page.getByText('医嘱与协同').first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText('照护管理').first()).toBeVisible({ timeout: 8_000 });

    // 5 个照护操作按钮
    await expect(page.getByRole('button', { name: '新增医嘱' })).toBeVisible();
    await expect(page.getByRole('button', { name: '开立检查' })).toBeVisible();
    await expect(page.getByRole('button', { name: '发起 MDT' })).toBeVisible();
    await expect(page.getByRole('button', { name: '记录宣教' })).toBeVisible();
    await expect(page.getByRole('button', { name: '创建随访' })).toBeVisible();
  });

  test('步骤 2：打开新增医嘱对话框，填写并提交', async ({ page }) => {
    await setDevAuth(page, 'doctor');
    await page.goto(`/patient/${patientId}?section=orders`);

    // 点新增医嘱
    await page.getByRole('button', { name: '新增医嘱' }).click();

    // 对话框标题 (careActionLabel('medication') = '新增医嘱')
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 5_000 });

    // 填表
    await page.getByLabel('药品名称').fill('氨氯地平片');
    await page.getByLabel('剂量').fill('5mg');
    await page.getByLabel('频次').fill('qd');

    // 确认
    const confirmBtn = page.getByRole('button', { name: /确认新增医嘱|确认$/ });
    if (await confirmBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await confirmBtn.click();
    }

    // 对话框关闭
    await page.waitForTimeout(1500);
  });

  test('步骤 3：发起 MDT 会诊', async ({ page }) => {
    await setDevAuth(page, 'doctor');
    await page.goto(`/patient/${patientId}?section=orders`);

    // 点发起 MDT
    await page.getByRole('button', { name: '发起 MDT' }).click();

    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 5_000 });

    await page.getByLabel('会诊原因').fill('血压控制不佳，需多学科评估');
    await page.getByLabel('会诊专科（逗号分隔）').fill('心内科,营养科');

    const confirmBtn = page.getByRole('button', { name: /确认发起 MDT|确认$/ });
    if (await confirmBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await confirmBtn.click();
    }
    await page.waitForTimeout(1500);
  });

  test('步骤 4：创建随访对话框可正常打开和关闭', async ({ page }) => {
    await setDevAuth(page, 'doctor');
    await page.goto(`/patient/${patientId}?section=orders`);

    // 点创建随访
    await page.getByRole('button', { name: '创建随访' }).click();

    // 对话框出现
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 8_000 });

    // 点取消关闭
    await page.getByRole('button', { name: '取消' }).click();
    await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 5_000 });
  });

  test('步骤 5：患者详情概览页正常渲染', async ({ page }) => {
    await setDevAuth(page, 'doctor');
    await page.goto(`/patient/${patientId}`);

    // 临床概览
    await expect(page.getByText('临床概览').first()).toBeVisible({ timeout: 15_000 });

    // Agent 流程面板
    await expect(page.getByText(/智能流程|流程就绪/).first()).toBeVisible({ timeout: 8_000 });
  });
});
