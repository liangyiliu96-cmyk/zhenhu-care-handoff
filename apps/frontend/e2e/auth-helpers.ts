import { Page, request as playwrightRequest } from '@playwright/test';

const BACKEND = process.env.E2E_BACKEND_URL ?? 'http://127.0.0.1:8001';

/**
 * Delete a patient from the state store via the backend's clear-expired
 * and manual DB cleanup endpoints, so the fixture can be reloaded cleanly.
 */
async function clearPatientState(_patientId: string) {
  const context = await playwrightRequest.newContext();
  const headers = {
    'Content-Type': 'application/json',
    'x-user-id': 'e2e-doctor',
    'x-role': 'doctor',
  };
  // Use clear-expired to remove from in-memory + backend
  await context.post(`${BACKEND}/inpatient/clear-expired`, { headers }).catch(() => {});
  await context.dispose();
}

/**
 * Seed backend state before E2E flows.
 * Clears stale state then loads the dashboard-care fixture.
 */
export async function seedTestPatient(): Promise<string> {
  await clearPatientState('demo-dashboard-care');

  const context = await playwrightRequest.newContext();
  const headers = {
    'Content-Type': 'application/json',
    'x-user-id': 'e2e-doctor',
    'x-role': 'doctor',
  };

  const res = await context.post(`${BACKEND}/inpatient/fixtures/load/dashboard-care`, { headers });
  const body = await res.json();
  await context.dispose();

  if (!res.ok()) {
    // Retry after another cleanup — the first clear may not reach SQLite DML
    await clearPatientState('demo-dashboard-care');
    const ctx2 = await playwrightRequest.newContext();
    const res2 = await ctx2.post(`${BACKEND}/inpatient/fixtures/load/dashboard-care`, { headers });
    const body2 = await res2.json();
    await ctx2.dispose();
    if (!res2.ok()) throw new Error(`Fixture seed failed: ${res2.status()} ${JSON.stringify(body2)}`);
    return body2.data?.patient_id ?? (body2 as { patient_id?: string }).patient_id ?? '';
  }

  return body.data?.patient_id ?? (body as { patient_id?: string }).patient_id ?? '';
}

/**
 * Inject auth headers into the browser sessionStorage so the
 * frontend auth-bridge picks them up before any API call.
 */
export async function setDevAuth(page: Page, role: 'doctor' | 'nurse' = 'doctor') {
  await page.addInitScript((r: string) => {
    sessionStorage.setItem('zhenhu_role', r);
    sessionStorage.setItem('zhenhu_actor_id', r === 'doctor' ? 'e2e-doctor' : 'e2e-nurse');
    sessionStorage.setItem('zhenhu_title', r === 'doctor' ? '主治医师' : '主管护师');
    sessionStorage.setItem('zhenhu_department', '心内科');
  }, role);
}
