"""模拟患者数据——供开发测试使用。每个患者包含完整入院→出院链路数据。"""

PATIENTS = {
    "pat-htn-001": {
        "name": "高血压患者-张建国",
        "description": "65岁男性，高血压10年，本次因血压控制不佳入院",
        "disease_id": "hypertension",
        "patient_data": {
            "age": 65, "gender": "male", "bmi": 28, "pain_score": 2,
            "pain_location": "无", "reduced_mobility": False,
        },
        "patient_history": {
            "smoking": True, "family_history_cvd": True,
            "comorbidities": ["hypertension", "obesity"],
            "prior_hospitalization": True,
            "medications": ["氨氯地平", "厄贝沙坦"],
        },
        "allergies": [],
        "vital_signs_sequence": [
            # 入院时偏高→用药后逐步稳定
            {"blood_pressure": "175/105", "systolic_mmhg": 175, "diastolic_mmhg": 105, "heart_rate": 88, "spo2": 97, "temperature": 36.6},
            {"blood_pressure": "168/100", "systolic_mmhg": 168, "diastolic_mmhg": 100, "heart_rate": 82, "spo2": 98, "temperature": 36.5},
            {"blood_pressure": "155/95", "systolic_mmhg": 155, "diastolic_mmhg": 95, "heart_rate": 78, "spo2": 98, "temperature": 36.4},
            {"blood_pressure": "142/88", "systolic_mmhg": 142, "diastolic_mmhg": 88, "heart_rate": 76, "spo2": 98, "temperature": 36.5},
            {"blood_pressure": "138/85", "systolic_mmhg": 138, "diastolic_mmhg": 85, "heart_rate": 74, "spo2": 98, "temperature": 36.5},
            {"blood_pressure": "135/82", "systolic_mmhg": 135, "diastolic_mmhg": 82, "heart_rate": 72, "spo2": 99, "temperature": 36.4},
            {"blood_pressure": "130/80", "systolic_mmhg": 130, "diastolic_mmhg": 80, "heart_rate": 72, "spo2": 98, "temperature": 36.5},
        ],
        "lab_results": [
            {"name": "creatinine", "value": 88, "unit": "μmol/L"},
            {"name": "potassium", "value": 4.1, "unit": "mmol/L"},
        ],
        "expected_discharge": True,  # 预计可正常出院
    },

    "pat-hf-001": {
        "name": "心衰患者-李秀英",
        "description": "72岁女性，心衰病史3年，NYHA III级，因气促水肿加重入院",
        "disease_id": "heart_failure",
        "patient_data": {
            "age": 72, "gender": "female", "bmi": 26, "pain_score": 1,
            "reduced_mobility": True,
        },
        "patient_history": {
            "smoking": False,
            "comorbidities": ["heart_failure", "hypertension", "ckd_stage3"],
            "prior_hospitalization": True,
            "medications": ["呋塞米", "螺内酯", "培哚普利", "美托洛尔", "达格列净"],
        },
        "allergies": ["青霉素过敏"],
        "vital_signs_sequence": [
            {"blood_pressure": "100/65", "systolic_mmhg": 100, "diastolic_mmhg": 65, "heart_rate": 95, "spo2": 93, "temperature": 36.8, "weight": 72.5},
            {"blood_pressure": "105/68", "systolic_mmhg": 105, "diastolic_mmhg": 68, "heart_rate": 88, "spo2": 94, "temperature": 36.6, "weight": 71.8},
            {"blood_pressure": "108/70", "systolic_mmhg": 108, "diastolic_mmhg": 70, "heart_rate": 82, "spo2": 95, "temperature": 36.5, "weight": 70.5},
            {"blood_pressure": "112/72", "systolic_mmhg": 112, "diastolic_mmhg": 72, "heart_rate": 78, "spo2": 96, "temperature": 36.5, "weight": 70.0},
            {"blood_pressure": "115/74", "systolic_mmhg": 115, "diastolic_mmhg": 74, "heart_rate": 75, "spo2": 96, "temperature": 36.4, "weight": 69.8},
            {"blood_pressure": "118/75", "systolic_mmhg": 118, "diastolic_mmhg": 75, "heart_rate": 74, "spo2": 97, "temperature": 36.5, "weight": 69.5},
        ],
        "lab_results": [
            {"name": "nt_probnp", "value": 3500, "unit": "pg/mL"},
            {"name": "creatinine", "value": 130, "unit": "μmol/L"},
            {"name": "potassium", "value": 4.5, "unit": "mmol/L"},
        ],
        "expected_discharge": True,
    },

    "pat-dm-001": {
        "name": "糖尿病患者-王建国",
        "description": "58岁男性，2型糖尿病8年，因血糖控制不佳+酮症入院",
        "disease_id": "diabetes",
        "patient_data": {
            "age": 58, "gender": "male", "bmi": 31, "pain_score": 0,
            "reduced_mobility": False,
        },
        "patient_history": {
            "smoking": True,
            "comorbidities": ["diabetes", "hypertension", "obesity", "neuropathy"],
            "prior_hospitalization": True,
            "hypoglycemia_history": True,
            "medications": ["二甲双胍", "格列美脲", "胰岛素"],
        },
        "allergies": [],
        "vital_signs_sequence": [
            {"blood_glucose_fasting": 14.2, "blood_pressure": "145/90", "systolic_mmhg": 145, "diastolic_mmhg": 90, "heart_rate": 85, "spo2": 98, "temperature": 36.7},
            {"blood_glucose_fasting": 12.5, "blood_pressure": "140/88", "systolic_mmhg": 140, "diastolic_mmhg": 88, "heart_rate": 82, "spo2": 98, "temperature": 36.5},
            {"blood_glucose_fasting": 10.8, "blood_pressure": "138/85", "systolic_mmhg": 138, "diastolic_mmhg": 85, "heart_rate": 80, "spo2": 98, "temperature": 36.5},
            {"blood_glucose_fasting": 8.5, "blood_pressure": "135/82", "systolic_mmhg": 135, "diastolic_mmhg": 82, "heart_rate": 78, "spo2": 99, "temperature": 36.4},
            {"blood_glucose_fasting": 7.2, "blood_pressure": "132/80", "systolic_mmhg": 132, "diastolic_mmhg": 80, "heart_rate": 76, "spo2": 98, "temperature": 36.5},
            {"blood_glucose_fasting": 6.5, "blood_pressure": "130/80", "systolic_mmhg": 130, "diastolic_mmhg": 80, "heart_rate": 74, "spo2": 98, "temperature": 36.5},
        ],
        "lab_results": [
            {"name": "hba1c", "value": 9.2, "unit": "%"},
            {"name": "blood_ketone", "value": 0.8, "unit": "mmol/L"},
            {"name": "creatinine", "value": 75, "unit": "μmol/L"},
        ],
        "expected_discharge": True,
    },

    # ===== 新增11个病种 =====

    "pat-cad-001": {
        "name": "冠心病患者-陈志强",
        "description": "62岁男性，冠心病+PCI术后3天，因胸闷再发入院观察",
        "disease_id": "cad",
        "patient_data": {
            "age": 62, "gender": "male", "bmi": 27, "pain_score": 3,
            "pain_location": "胸骨后", "reduced_mobility": True,
        },
        "patient_history": {
            "smoking": True,
            "comorbidities": ["coronary_artery_disease", "hypertension", "hyperlipidemia"],
            "prior_hospitalization": True,
            "medications": ["阿司匹林", "氯吡格雷", "阿托伐他汀", "美托洛尔"],
        },
        "allergies": [],
        "vital_signs_sequence": [
            {"blood_pressure": "150/95", "systolic_mmhg": 150, "diastolic_mmhg": 95, "heart_rate": 92, "spo2": 96, "temperature": 36.7, "troponin": 0.12, "ldl": 3.5},
            {"blood_pressure": "145/90", "systolic_mmhg": 145, "diastolic_mmhg": 90, "heart_rate": 85, "spo2": 97, "temperature": 36.5, "troponin": 0.08, "ldl": 3.5},
            {"blood_pressure": "140/88", "systolic_mmhg": 140, "diastolic_mmhg": 88, "heart_rate": 80, "spo2": 97, "temperature": 36.4, "troponin": 0.05, "ldl": 3.5},
            {"blood_pressure": "135/85", "systolic_mmhg": 135, "diastolic_mmhg": 85, "heart_rate": 76, "spo2": 98, "temperature": 36.5, "troponin": 0.03, "ldl": 3.5},
            {"blood_pressure": "130/82", "systolic_mmhg": 130, "diastolic_mmhg": 82, "heart_rate": 74, "spo2": 98, "temperature": 36.5, "troponin": 0.02, "ldl": 3.5},
            {"blood_pressure": "128/80", "systolic_mmhg": 128, "diastolic_mmhg": 80, "heart_rate": 72, "spo2": 98, "temperature": 36.4, "troponin": 0.01, "ldl": 3.5},
            {"blood_pressure": "125/78", "systolic_mmhg": 125, "diastolic_mmhg": 78, "heart_rate": 70, "spo2": 99, "temperature": 36.5, "troponin": 0.01, "ldl": 3.5},
        ],
        "lab_results": [
            {"name": "troponin", "value": 0.12, "unit": "ng/mL"},
            {"name": "ldl", "value": 3.5, "unit": "mmol/L"},
            {"name": "creatinine", "value": 82, "unit": "μmol/L"},
        ],
        "expected_discharge": True,
    },

    "pat-stroke-001": {
        "name": "脑卒中患者-赵秀兰",
        "description": "70岁女性，缺血性脑卒中，左侧肢体无力，NIHSS 8分入院",
        "disease_id": "stroke",
        "patient_data": {
            "age": 70, "gender": "female", "bmi": 24, "pain_score": 1,
            "pain_location": "无", "reduced_mobility": True,
        },
        "patient_history": {
            "smoking": False,
            "comorbidities": ["stroke", "hypertension", "atrial_fibrillation"],
            "prior_hospitalization": True,
            "medications": ["氯吡格雷", "阿托伐他汀", "氨氯地平", "华法林"],
        },
        "allergies": ["磺胺类过敏"],
        "vital_signs_sequence": [
            {"blood_pressure": "175/100", "systolic_mmhg": 175, "diastolic_mmhg": 100, "heart_rate": 82, "spo2": 96, "temperature": 36.8, "nihss_score": 8, "gcs": 14, "blood_glucose": 8.5},
            {"blood_pressure": "168/95", "systolic_mmhg": 168, "diastolic_mmhg": 95, "heart_rate": 80, "spo2": 97, "temperature": 36.6, "nihss_score": 7, "gcs": 14, "blood_glucose": 7.8},
            {"blood_pressure": "160/90", "systolic_mmhg": 160, "diastolic_mmhg": 90, "heart_rate": 78, "spo2": 97, "temperature": 36.5, "nihss_score": 6, "gcs": 15, "blood_glucose": 7.2},
            {"blood_pressure": "150/88", "systolic_mmhg": 150, "diastolic_mmhg": 88, "heart_rate": 76, "spo2": 98, "temperature": 36.4, "nihss_score": 5, "gcs": 15, "blood_glucose": 6.8},
            {"blood_pressure": "145/85", "systolic_mmhg": 145, "diastolic_mmhg": 85, "heart_rate": 74, "spo2": 98, "temperature": 36.5, "nihss_score": 4, "gcs": 15, "blood_glucose": 6.5},
            {"blood_pressure": "138/82", "systolic_mmhg": 138, "diastolic_mmhg": 82, "heart_rate": 72, "spo2": 98, "temperature": 36.5, "nihss_score": 3, "gcs": 15, "blood_glucose": 6.2},
        ],
        "lab_results": [
            {"name": "nihss_score", "value": 8, "unit": "分"},
            {"name": "gcs", "value": 14, "unit": "分"},
            {"name": "ldl", "value": 3.2, "unit": "mmol/L"},
        ],
        "expected_discharge": True,
    },

    "pat-copd-001": {
        "name": "COPD患者-刘德明",
        "description": "68岁男性，COPD病史12年，本次急性加重入院，呼吸困难III级",
        "disease_id": "copd",
        "patient_data": {
            "age": 68, "gender": "male", "bmi": 23, "pain_score": 1,
            "pain_location": "无", "reduced_mobility": True,
        },
        "patient_history": {
            "smoking": True,
            "comorbidities": ["copd", "hypertension", "osteoporosis"],
            "prior_hospitalization": True,
            "medications": ["噻托溴铵", "沙美特罗替卡松", "茶碱缓释片"],
        },
        "allergies": [],
        "vital_signs_sequence": [
            {"spo2": 86, "respiratory_rate": 30, "heart_rate": 108, "blood_pressure": "135/85", "systolic_mmhg": 135, "diastolic_mmhg": 85, "temperature": 37.2, "paco2": 55},
            {"spo2": 88, "respiratory_rate": 28, "heart_rate": 102, "blood_pressure": "132/82", "systolic_mmhg": 132, "diastolic_mmhg": 82, "temperature": 37.0, "paco2": 52},
            {"spo2": 90, "respiratory_rate": 26, "heart_rate": 98, "blood_pressure": "130/80", "systolic_mmhg": 130, "diastolic_mmhg": 80, "temperature": 36.8, "paco2": 50},
            {"spo2": 91, "respiratory_rate": 24, "heart_rate": 94, "blood_pressure": "128/78", "systolic_mmhg": 128, "diastolic_mmhg": 78, "temperature": 36.6, "paco2": 48},
            {"spo2": 92, "respiratory_rate": 22, "heart_rate": 90, "blood_pressure": "125/78", "systolic_mmhg": 125, "diastolic_mmhg": 78, "temperature": 36.5, "paco2": 46},
            {"spo2": 93, "respiratory_rate": 20, "heart_rate": 86, "blood_pressure": "125/76", "systolic_mmhg": 125, "diastolic_mmhg": 76, "temperature": 36.5, "paco2": 44},
        ],
        "lab_results": [
            {"name": "paco2", "value": 55, "unit": "mmHg"},
            {"name": "fev1_percent", "value": 42, "unit": "%"},
            {"name": "crp", "value": 25, "unit": "mg/L"},
        ],
        "expected_discharge": True,
    },

    "pat-pneumonia-001": {
        "name": "肺炎患者-周明芳",
        "description": "55岁女性，社区获得性肺炎，发热咳嗽5天，右下肺浸润影",
        "disease_id": "pneumonia",
        "patient_data": {
            "age": 55, "gender": "female", "bmi": 25, "pain_score": 4,
            "pain_location": "右下胸", "reduced_mobility": True,
        },
        "patient_history": {
            "smoking": False,
            "comorbidities": ["community_acquired_pneumonia", "asthma"],
            "prior_hospitalization": False,
            "medications": ["头孢曲松", "阿奇霉素", "沙丁胺醇"],
        },
        "allergies": ["头孢类过敏史待确认"],
        "vital_signs_sequence": [
            {"temperature": 39.2, "spo2": 90, "respiratory_rate": 30, "heart_rate": 105, "blood_pressure": "105/65", "systolic_mmhg": 105, "diastolic_mmhg": 65},
            {"temperature": 38.5, "spo2": 91, "respiratory_rate": 28, "heart_rate": 100, "blood_pressure": "108/68", "systolic_mmhg": 108, "diastolic_mmhg": 68},
            {"temperature": 38.0, "spo2": 92, "respiratory_rate": 26, "heart_rate": 95, "blood_pressure": "110/70", "systolic_mmhg": 110, "diastolic_mmhg": 70},
            {"temperature": 37.5, "spo2": 93, "respiratory_rate": 24, "heart_rate": 90, "blood_pressure": "112/70", "systolic_mmhg": 112, "diastolic_mmhg": 70},
            {"temperature": 37.0, "spo2": 94, "respiratory_rate": 22, "heart_rate": 85, "blood_pressure": "115/72", "systolic_mmhg": 115, "diastolic_mmhg": 72},
            {"temperature": 36.6, "spo2": 95, "respiratory_rate": 20, "heart_rate": 82, "blood_pressure": "115/75", "systolic_mmhg": 115, "diastolic_mmhg": 75},
            {"temperature": 36.5, "spo2": 96, "respiratory_rate": 18, "heart_rate": 78, "blood_pressure": "118/75", "systolic_mmhg": 118, "diastolic_mmhg": 75},
        ],
        "lab_results": [
            {"name": "crp", "value": 85, "unit": "mg/L"},
            {"name": "wbc", "value": 14.2, "unit": "×10⁹/L"},
            {"name": "procalcitonin", "value": 2.5, "unit": "ng/mL"},
        ],
        "expected_discharge": True,
    },

    "pat-ckd-001": {
        "name": "慢性肾病患者-孙志明",
        "description": "60岁男性，CKD3期，糖尿病肾病背景，因水肿加重+eGFR下降入院",
        "disease_id": "ckd",
        "patient_data": {
            "age": 60, "gender": "male", "bmi": 28, "pain_score": 1,
            "pain_location": "无", "reduced_mobility": True,
        },
        "patient_history": {
            "smoking": False,
            "comorbidities": ["ckd_stage3", "diabetes", "hypertension", "anemia"],
            "prior_hospitalization": True,
            "medications": ["厄贝沙坦", "呋塞米", "碳酸氢钠", "促红素"],
        },
        "allergies": ["造影剂过敏"],
        "vital_signs_sequence": [
            {"blood_pressure": "155/92", "systolic_mmhg": 155, "diastolic_mmhg": 92, "heart_rate": 80, "spo2": 97, "temperature": 36.6, "egfr": 35, "potassium": 5.6, "hemoglobin": 8.5, "bicarbonate": 17, "calcium": 2.05, "phosphorus": 1.85, "weight": 78.0},
            {"blood_pressure": "150/90", "systolic_mmhg": 150, "diastolic_mmhg": 90, "heart_rate": 78, "spo2": 97, "temperature": 36.5, "egfr": 36, "potassium": 5.3, "hemoglobin": 8.5, "bicarbonate": 18, "calcium": 2.08, "phosphorus": 1.82, "weight": 77.5},
            {"blood_pressure": "145/88", "systolic_mmhg": 145, "diastolic_mmhg": 88, "heart_rate": 76, "spo2": 98, "temperature": 36.5, "egfr": 38, "potassium": 5.0, "hemoglobin": 8.5, "bicarbonate": 19, "calcium": 2.10, "phosphorus": 1.78, "weight": 77.0},
            {"blood_pressure": "140/85", "systolic_mmhg": 140, "diastolic_mmhg": 85, "heart_rate": 76, "spo2": 98, "temperature": 36.4, "egfr": 40, "potassium": 4.8, "hemoglobin": 8.8, "bicarbonate": 20, "calcium": 2.12, "phosphorus": 1.72, "weight": 76.5},
            {"blood_pressure": "138/82", "systolic_mmhg": 138, "diastolic_mmhg": 82, "heart_rate": 74, "spo2": 98, "temperature": 36.5, "egfr": 42, "potassium": 4.6, "hemoglobin": 8.8, "bicarbonate": 21, "calcium": 2.15, "phosphorus": 1.68, "weight": 76.0},
            {"blood_pressure": "135/80", "systolic_mmhg": 135, "diastolic_mmhg": 80, "heart_rate": 72, "spo2": 98, "temperature": 36.5, "egfr": 44, "potassium": 4.4, "hemoglobin": 9.0, "bicarbonate": 22, "calcium": 2.18, "phosphorus": 1.62, "weight": 75.5},
        ],
        "lab_results": [
            {"name": "egfr", "value": 35, "unit": "ml/min"},
            {"name": "potassium", "value": 5.6, "unit": "mmol/L"},
            {"name": "hemoglobin", "value": 8.5, "unit": "g/dL"},
            {"name": "creatinine", "value": 185, "unit": "μmol/L"},
        ],
        "expected_discharge": True,
    },

    "pat-aki-001": {
        "name": "急性肾损伤患者-赵磊",
        "description": "45岁男性，冠脉造影后3天，造影剂相关AKI，少尿+肌酐飙升",
        "disease_id": "aki",
        "patient_data": {
            "age": 45, "gender": "male", "bmi": 26, "pain_score": 2,
            "pain_location": "腰部酸胀", "reduced_mobility": False,
        },
        "patient_history": {
            "smoking": True,
            "comorbidities": ["aki", "hypertension", "coronary_artery_disease"],
            "prior_hospitalization": True,
            "medications": ["呋塞米", "氨氯地平", "阿司匹林"],
        },
        "allergies": ["造影剂过敏"],
        "vital_signs_sequence": [
            {"urine_output": 20, "creatinine_vs": 280, "potassium": 5.8, "blood_pressure": "95/62", "systolic_mmhg": 95, "diastolic_mmhg": 62, "bun": 18, "bicarbonate": 16, "heart_rate": 88, "spo2": 97, "temperature": 36.8, "weight": 80.0},
            {"urine_output": 25, "creatinine_vs": 260, "potassium": 5.6, "blood_pressure": "98/65", "systolic_mmhg": 98, "diastolic_mmhg": 65, "bun": 17, "bicarbonate": 17, "heart_rate": 85, "spo2": 97, "temperature": 36.6, "weight": 79.5},
            {"urine_output": 30, "creatinine_vs": 240, "potassium": 5.3, "blood_pressure": "102/68", "systolic_mmhg": 102, "diastolic_mmhg": 68, "bun": 16, "bicarbonate": 18, "heart_rate": 82, "spo2": 98, "temperature": 36.5, "weight": 79.0},
            {"urine_output": 35, "creatinine_vs": 210, "potassium": 5.0, "blood_pressure": "105/70", "systolic_mmhg": 105, "diastolic_mmhg": 70, "bun": 14, "bicarbonate": 19, "heart_rate": 80, "spo2": 98, "temperature": 36.5, "weight": 78.5},
            {"urine_output": 40, "creatinine_vs": 180, "potassium": 4.8, "blood_pressure": "108/70", "systolic_mmhg": 108, "diastolic_mmhg": 70, "bun": 12, "bicarbonate": 20, "heart_rate": 78, "spo2": 98, "temperature": 36.4, "weight": 78.0},
            {"urine_output": 50, "creatinine_vs": 150, "potassium": 4.5, "blood_pressure": "112/72", "systolic_mmhg": 112, "diastolic_mmhg": 72, "bun": 10, "bicarbonate": 22, "heart_rate": 76, "spo2": 98, "temperature": 36.5, "weight": 77.5},
        ],
        "lab_results": [
            {"name": "creatinine", "value": 280, "unit": "μmol/L"},
            {"name": "bun", "value": 18, "unit": "mmol/L"},
            {"name": "potassium", "value": 5.8, "unit": "mmol/L"},
        ],
        "expected_discharge": True,
    },

    "pat-cirrhosis-001": {
        "name": "肝硬化患者-黄国栋",
        "description": "58岁男性，乙肝肝硬化失代偿期，Child-Pugh B级，腹水中度+轻度肝性脑病",
        "disease_id": "cirrhosis",
        "patient_data": {
            "age": 58, "gender": "male", "bmi": 22, "pain_score": 3,
            "pain_location": "右上腹", "reduced_mobility": True,
        },
        "patient_history": {
            "smoking": False,
            "comorbidities": ["cirrhosis", "hepatitis_b", "portal_hypertension", "ascites"],
            "prior_hospitalization": True,
            "medications": ["螺内酯", "呋塞米", "恩替卡韦", "乳果糖", "利福昔明"],
        },
        "allergies": [],
        "vital_signs_sequence": [
            {"blood_pressure": "95/60", "systolic_mmhg": 95, "diastolic_mmhg": 60, "heart_rate": 95, "temperature": 36.8, "weight": 72.0, "west_haven_grade": 2, "inr": 1.7, "bilirubin": 42, "albumin": 26},
            {"blood_pressure": "98/62", "systolic_mmhg": 98, "diastolic_mmhg": 62, "heart_rate": 90, "temperature": 36.6, "weight": 71.2, "west_haven_grade": 1, "inr": 1.6, "bilirubin": 40, "albumin": 26},
            {"blood_pressure": "100/65", "systolic_mmhg": 100, "diastolic_mmhg": 65, "heart_rate": 86, "temperature": 36.5, "weight": 70.5, "west_haven_grade": 1, "inr": 1.5, "bilirubin": 38, "albumin": 27},
            {"blood_pressure": "102/68", "systolic_mmhg": 102, "diastolic_mmhg": 68, "heart_rate": 84, "temperature": 36.5, "weight": 69.8, "west_haven_grade": 0, "inr": 1.4, "bilirubin": 35, "albumin": 28},
            {"blood_pressure": "105/70", "systolic_mmhg": 105, "diastolic_mmhg": 70, "heart_rate": 82, "temperature": 36.4, "weight": 69.2, "west_haven_grade": 0, "inr": 1.3, "bilirubin": 32, "albumin": 29},
            {"blood_pressure": "108/70", "systolic_mmhg": 108, "diastolic_mmhg": 70, "heart_rate": 80, "temperature": 36.5, "weight": 68.5, "west_haven_grade": 0, "inr": 1.2, "bilirubin": 30, "albumin": 30},
        ],
        "lab_results": [
            {"name": "inr", "value": 1.7, "unit": ""},
            {"name": "bilirubin", "value": 42, "unit": "μmol/L"},
            {"name": "albumin", "value": 26, "unit": "g/L"},
            {"name": "creatinine", "value": 95, "unit": "μmol/L"},
        ],
        "expected_discharge": True,
    },

    "pat-gi_bleeding-001": {
        "name": "消化道出血患者-吴国强",
        "description": "50岁男性，十二指肠溃疡并出血，入院时黑便+血红蛋白下降",
        "disease_id": "gi_bleeding",
        "patient_data": {
            "age": 50, "gender": "male", "bmi": 24, "pain_score": 5,
            "pain_location": "上腹部", "reduced_mobility": True,
        },
        "patient_history": {
            "smoking": True,
            "comorbidities": ["duodenal_ulcer", "hypertension"],
            "prior_hospitalization": True,
            "medications": ["奥美拉唑", "铝碳酸镁", "氨氯地平"],
        },
        "allergies": [],
        "vital_signs_sequence": [
            {"blood_pressure": "88/55", "systolic_mmhg": 88, "diastolic_mmhg": 55, "heart_rate": 112, "spo2": 94, "temperature": 36.6, "hemoglobin": 6.5, "platelet": 65, "inr": 2.2, "bun": 16},
            {"blood_pressure": "92/58", "systolic_mmhg": 92, "diastolic_mmhg": 58, "heart_rate": 108, "spo2": 95, "temperature": 36.5, "hemoglobin": 7.0, "platelet": 70, "inr": 2.0, "bun": 15},
            {"blood_pressure": "95/62", "systolic_mmhg": 95, "diastolic_mmhg": 62, "heart_rate": 102, "spo2": 95, "temperature": 36.5, "hemoglobin": 7.5, "platelet": 80, "inr": 1.8, "bun": 14},
            {"blood_pressure": "100/65", "systolic_mmhg": 100, "diastolic_mmhg": 65, "heart_rate": 98, "spo2": 96, "temperature": 36.4, "hemoglobin": 8.0, "platelet": 95, "inr": 1.6, "bun": 12},
            {"blood_pressure": "105/68", "systolic_mmhg": 105, "diastolic_mmhg": 68, "heart_rate": 92, "spo2": 97, "temperature": 36.5, "hemoglobin": 8.5, "platelet": 110, "inr": 1.4, "bun": 10},
            {"blood_pressure": "110/70", "systolic_mmhg": 110, "diastolic_mmhg": 70, "heart_rate": 88, "spo2": 97, "temperature": 36.5, "hemoglobin": 9.0, "platelet": 130, "inr": 1.2, "bun": 8},
        ],
        "lab_results": [
            {"name": "hemoglobin", "value": 6.5, "unit": "g/dL"},
            {"name": "platelet", "value": 65, "unit": "×10⁹/L"},
            {"name": "inr", "value": 2.2, "unit": ""},
            {"name": "bun", "value": 16, "unit": "mmol/L"},
        ],
        "expected_discharge": True,
    },

    "pat-hyperthyroidism-001": {
        "name": "甲亢患者-林晓燕",
        "description": "35岁女性，Graves病初发，心悸手抖体重下降，HR 120次/分入院",
        "disease_id": "hyperthyroidism",
        "patient_data": {
            "age": 35, "gender": "female", "bmi": 20, "pain_score": 0,
            "pain_location": "无", "reduced_mobility": False,
        },
        "patient_history": {
            "smoking": False,
            "comorbidities": ["hyperthyroidism", "mild_anxiety"],
            "prior_hospitalization": False,
            "medications": ["甲巯咪唑", "普萘洛尔"],
        },
        "allergies": [],
        "vital_signs_sequence": [
            {"heart_rate": 120, "blood_pressure": "145/85", "systolic_mmhg": 145, "diastolic_mmhg": 85, "temperature": 37.5, "weight": 48.5, "wbc": 3.8, "spo2": 98},
            {"heart_rate": 112, "blood_pressure": "140/82", "systolic_mmhg": 140, "diastolic_mmhg": 82, "temperature": 37.2, "weight": 48.5, "wbc": 3.9, "spo2": 98},
            {"heart_rate": 105, "blood_pressure": "135/80", "systolic_mmhg": 135, "diastolic_mmhg": 80, "temperature": 37.0, "weight": 48.8, "wbc": 4.0, "spo2": 98},
            {"heart_rate": 98, "blood_pressure": "132/78", "systolic_mmhg": 132, "diastolic_mmhg": 78, "temperature": 36.8, "weight": 49.0, "wbc": 4.2, "spo2": 99},
            {"heart_rate": 92, "blood_pressure": "128/76", "systolic_mmhg": 128, "diastolic_mmhg": 76, "temperature": 36.6, "weight": 49.2, "wbc": 4.5, "spo2": 99},
            {"heart_rate": 88, "blood_pressure": "125/75", "systolic_mmhg": 125, "diastolic_mmhg": 75, "temperature": 36.5, "weight": 49.5, "wbc": 4.8, "spo2": 99},
        ],
        "lab_results": [
            {"name": "tsh", "value": 0.01, "unit": "mIU/L"},
            {"name": "ft4", "value": 45, "unit": "pmol/L"},
            {"name": "ft3", "value": 18, "unit": "pmol/L"},
            {"name": "wbc", "value": 3.8, "unit": "×10⁹/L"},
        ],
        "expected_discharge": True,
    },

    "pat-post_surgery-001": {
        "name": "术后恢复患者-何丽华",
        "description": "45岁女性，腹腔镜胆囊切除术后第3天，伤口愈合良好，肠道功能恢复中",
        "disease_id": "post_surgery",
        "patient_data": {
            "age": 45, "gender": "female", "bmi": 26, "pain_score": 5,
            "pain_location": "右上腹切口", "reduced_mobility": True,
        },
        "patient_history": {
            "smoking": False,
            "comorbidities": ["cholecystolithiasis", "mild_hypertension"],
            "prior_hospitalization": False,
            "medications": ["头孢呋辛", "对乙酰氨基酚", "氨氯地平"],
        },
        "allergies": [],
        "vital_signs_sequence": [
            {"blood_pressure": "128/82", "systolic_mmhg": 128, "diastolic_mmhg": 82, "heart_rate": 88, "temperature": 37.5, "spo2": 96, "pain_score_vs": 6, "urine_output": 35},
            {"blood_pressure": "125/80", "systolic_mmhg": 125, "diastolic_mmhg": 80, "heart_rate": 85, "temperature": 37.2, "spo2": 97, "pain_score_vs": 5, "urine_output": 40},
            {"blood_pressure": "122/78", "systolic_mmhg": 122, "diastolic_mmhg": 78, "heart_rate": 82, "temperature": 37.0, "spo2": 97, "pain_score_vs": 4, "urine_output": 45},
            {"blood_pressure": "120/76", "systolic_mmhg": 120, "diastolic_mmhg": 76, "heart_rate": 80, "temperature": 36.8, "spo2": 98, "pain_score_vs": 3, "urine_output": 50},
            {"blood_pressure": "118/75", "systolic_mmhg": 118, "diastolic_mmhg": 75, "heart_rate": 78, "temperature": 36.6, "spo2": 98, "pain_score_vs": 2, "urine_output": 55},
            {"blood_pressure": "118/74", "systolic_mmhg": 118, "diastolic_mmhg": 74, "heart_rate": 76, "temperature": 36.5, "spo2": 98, "pain_score_vs": 2, "urine_output": 55},
        ],
        "lab_results": [
            {"name": "wbc", "value": 9.5, "unit": "×10⁹/L"},
            {"name": "crp", "value": 35, "unit": "mg/L"},
            {"name": "hemoglobin", "value": 11.5, "unit": "g/dL"},
        ],
        "expected_discharge": True,
    },

    "pat-tumor_chemo-001": {
        "name": "肿瘤化疗后患者-杨美华",
        "description": "55岁女性，乳腺癌术后化疗第3周期后，粒缺伴发热入院",
        "disease_id": "tumor_chemo",
        "patient_data": {
            "age": 55, "gender": "female", "bmi": 22, "pain_score": 4,
            "pain_location": "全身酸痛", "reduced_mobility": True,
        },
        "patient_history": {
            "smoking": False,
            "comorbidities": ["breast_cancer", "post_chemotherapy_bone_marrow_suppression", "mild_anemia"],
            "prior_hospitalization": True,
            "medications": ["G-CSF", "昂丹司琼", "对乙酰氨基酚", "曲妥珠单抗"],
        },
        "allergies": [],
        "vital_signs_sequence": [
            {"temperature": 38.8, "neutrophil_count": 0.3, "platelet": 18, "spo2": 94, "wbc": 1.5, "hemoglobin": 7.5, "creatinine_vs": 98, "blood_pressure": "105/65", "systolic_mmhg": 105, "diastolic_mmhg": 65, "heart_rate": 95},
            {"temperature": 38.2, "neutrophil_count": 0.4, "platelet": 22, "spo2": 95, "wbc": 1.8, "hemoglobin": 7.5, "creatinine_vs": 95, "blood_pressure": "108/68", "systolic_mmhg": 108, "diastolic_mmhg": 68, "heart_rate": 92},
            {"temperature": 37.8, "neutrophil_count": 0.6, "platelet": 28, "spo2": 95, "wbc": 2.0, "hemoglobin": 7.8, "creatinine_vs": 92, "blood_pressure": "110/70", "systolic_mmhg": 110, "diastolic_mmhg": 70, "heart_rate": 88},
            {"temperature": 37.2, "neutrophil_count": 0.8, "platelet": 35, "spo2": 96, "wbc": 2.5, "hemoglobin": 7.8, "creatinine_vs": 90, "blood_pressure": "112/70", "systolic_mmhg": 112, "diastolic_mmhg": 70, "heart_rate": 85},
            {"temperature": 36.8, "neutrophil_count": 1.1, "platelet": 50, "spo2": 97, "wbc": 3.0, "hemoglobin": 8.0, "creatinine_vs": 88, "blood_pressure": "115/72", "systolic_mmhg": 115, "diastolic_mmhg": 72, "heart_rate": 82},
            {"temperature": 36.5, "neutrophil_count": 1.5, "platelet": 65, "spo2": 97, "wbc": 3.5, "hemoglobin": 8.2, "creatinine_vs": 85, "blood_pressure": "115/75", "systolic_mmhg": 115, "diastolic_mmhg": 75, "heart_rate": 80},
        ],
        "lab_results": [
            {"name": "neutrophil_count", "value": 0.3, "unit": "×10⁹/L"},
            {"name": "wbc", "value": 1.5, "unit": "×10⁹/L"},
            {"name": "hemoglobin", "value": 7.5, "unit": "g/dL"},
            {"name": "platelet", "value": 18, "unit": "×10⁹/L"},
        ],
        "expected_discharge": True,
    },
}
