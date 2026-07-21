import { apiGet, apiPost } from '@/core/api-client';
import type { UserIdentity, LoginResponse } from '@/types/auth';

export async function fetchWhoami(): Promise<UserIdentity> {
  return apiGet<UserIdentity>('/inpatient/whoami');
}

export async function loginWithCredentials(
  jobNumber: string,
  password: string
): Promise<LoginResponse> {
  return apiPost<LoginResponse>('/inpatient/login', {
    job_number: jobNumber,
    password,
  });
}

export async function loginWithDevShortcut(shortcutId: string): Promise<LoginResponse> {
  return apiPost<LoginResponse>(`/inpatient/login/dev-shortcut/${encodeURIComponent(shortcutId)}`);
}
