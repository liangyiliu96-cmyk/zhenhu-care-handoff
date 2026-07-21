export type AssistantMode = 'doctor' | 'nurse' | 'pharmacist' | 'patient' | 'integrative';

export const ASSISTANT_META: Record<AssistantMode, {
  name: string;
  shortName: string;
  placeholder: string;
}> = {
  doctor: { name: '查房助手', shortName: '查房', placeholder: '输入查房、诊断或治疗问题' },
  nurse: { name: '护理助手', shortName: '护理', placeholder: '输入护理观察或操作问题' },
  pharmacist: { name: '用药助手', shortName: '用药', placeholder: '输入用药核对或相互作用问题' },
  patient: { name: '臻护健康小助手', shortName: '患教', placeholder: '输入健康、康复或复诊问题' },
  integrative: { name: '中西医协同助手', shortName: '中西医', placeholder: '输入中西医协同评估问题' },
};

export function defaultAssistantModeForRole(role?: string | null): AssistantMode {
  return role === 'nurse' ? 'nurse' : 'doctor';
}

export function globalAssistantModesForRole(role?: string | null): AssistantMode[] {
  return role === 'nurse' ? ['nurse'] : ['doctor', 'pharmacist'];
}
