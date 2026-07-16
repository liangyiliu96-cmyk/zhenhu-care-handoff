"""fhir-adapter 路由模块 —— Patient 查询、照护视图与 FHIR 操作端点。"""

from zhenhu.fhir.routes.patients import router as patients_router
from zhenhu.fhir.routes.fhir_ops import router as fhir_ops_router
from zhenhu.fhir.routes.patient_care import router as patient_care_router

__all__ = ["patients_router", "fhir_ops_router", "patient_care_router"]
