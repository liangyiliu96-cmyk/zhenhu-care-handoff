import { describe, expect, it } from 'vitest';

import { directoryPatientToNurseDetail, nursePatientDisplayName } from './nurse-patient-utils';

describe('directoryPatientToNurseDetail', () => {
  it('creates a read-only detail without inventing nursing write state', () => {
    const detail = directoryPatientToNurseDetail({
      patient_id: 'patient-1',
      name: '张三',
      disease: '心力衰竭',
      phase: 'monitoring',
      risk_level: 'high',
      round_count: 2,
      discharge_decision: null,
      has_pending_review: false,
      pending_review_type: null,
      alert_count: 1,
      latest_vs: { systolic: 138, diastolic: 82, heart_rate: 88, spo2: 96, temperature: 36.8 },
      document_count: 4,
    }, '心内科');

    expect(detail).toMatchObject({
      patient_id: 'patient-1',
      department: '心内科',
      writable: false,
      alert_count: 1,
      latest_vital_values: { systolic: 138, diastolic: 82, spo2: 96, temperature: 36.8 },
    });
    expect(detail.state_version).toBeUndefined();
  });

  it('keeps short fallback identifiers distinct in nursing queues', () => {
    expect(nursePatientDisplayName({ patient_id: 'cardio-nurse-hf-001', name: 'cardio-nur' })).toBe('cardio-nurse-hf-001');
    expect(nursePatientDisplayName({ patient_id: 'cardio-nurse-cad-001', name: '李秀英' })).toBe('李秀英');
  });
});
