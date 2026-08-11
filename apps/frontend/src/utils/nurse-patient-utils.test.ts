import { describe, expect, it } from 'vitest';

import { applyNursingTaskCompletion, directoryPatientToNurseDetail, nursePatientDisplayName } from './nurse-patient-utils';

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

describe('applyNursingTaskCompletion', () => {
  it('removes the completed task and advances the displayed state version', () => {
    const updated = applyNursingTaskCompletion({
      patient_id: 'patient-1',
      name: '张三',
      disease: '心力衰竭',
      department: '心内科',
      alert_count: 0,
      state_version: 4,
      open_task_count: 2,
      task_items: [
        { task_key: 'vitals:1', task_type: 'vital_signs', title: '记录体征', description: '', priority: 'high' },
        { task_key: 'care:1', task_type: 'nursing_action', title: '护理措施', description: '', priority: 'normal' },
      ],
      writable: true,
    }, 'vitals:1', 5);

    expect(updated.state_version).toBe(5);
    expect(updated.open_task_count).toBe(1);
    expect(updated.task_items?.map((item) => item.task_key)).toEqual(['care:1']);
  });
});
