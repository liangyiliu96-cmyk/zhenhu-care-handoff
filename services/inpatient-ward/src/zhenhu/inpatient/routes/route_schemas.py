"""路由请求/响应 Pydantic Schema。"""
from pydantic import BaseModel, Field


class AdmissionRequest(BaseModel):
    patient_id: str = Field(default="pat-demo-001", min_length=1)
    disease_id: str = Field(default="hypertension", min_length=1)


class VitalSignsRequest(BaseModel):
    blood_pressure: str | None = None
    systolic_mmhg: int | None = None
    diastolic_mmhg: int | None = None
    heart_rate: int | None = None
    spo2: int | None = None
    temperature: float | None = None
    additional: dict | None = None


class LabResultsRequest(BaseModel):
    name: str
    value: str | float
    unit: str = ""
