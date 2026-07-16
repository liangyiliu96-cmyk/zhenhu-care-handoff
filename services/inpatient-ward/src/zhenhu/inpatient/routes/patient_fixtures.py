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
}
