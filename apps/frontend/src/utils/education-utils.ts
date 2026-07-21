export type EducationMode = 'guidance' | 'emergency';

export function educationQuery(disease: string, mode: EducationMode): string {
  const subject = disease.trim() || '出院患者';
  return mode === 'emergency' ? `${subject} 出院后急诊识别与就医时机` : `${subject} 出院患者教育 用药 饮食 康复 随访`;
}
