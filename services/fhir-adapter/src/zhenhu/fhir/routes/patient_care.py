"""患者照护视图聚合端点 —— 阶段 0: 患者照护视图聚合。

GET /patient/{patient_id}/care-view  — 聚合患者信息、照护计划与知识材料
"""

from __future__ import annotations

import asyncio
import os
from datetime import date

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zhenhu.fhir.models import CarePlan, Encounter, Patient, get_session
from zhenhu.fhir.schemas import PatientCareViewResponse, UnifiedResponse

router = APIRouter(prefix="/patient", tags=["patient"])

# 阶段 0: 患者照护视图聚合 —— 知识库服务地址，支持环境变量覆盖
KNOWLEDGE_URL = os.environ.get("KNOWLEDGE_URL", "http://localhost:8200")


def _get_request_id(request: Request) -> str:
    """从请求上下文中提取 request_id。"""
    return getattr(request.state, "request_id", "unknown")


def _calc_age(birth_date: date | None) -> int | None:
    """根据出生日期计算年龄（周岁）。"""
    if birth_date is None:
        return None
    today = date.today()
    return today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )


async def _search_knowledge(
    http_client: httpx.AsyncClient, query: str
) -> list[dict]:
    """调用 knowledge-orchestrator 搜索知识材料。

    阶段 0: 患者照护视图聚合 —— 知识检索失败时返回空列表，不阻断主流程。

    Args:
        http_client: httpx 异步客户端。
        query: 搜索关键词。

    Returns:
        最多 3 条知识片段。
    """
    try:
        resp = await http_client.get(
            f"{KNOWLEDGE_URL}/knowledge/search",
            params={"q": query},
        )
        resp.raise_for_status()
        data = resp.json()
        # 兼容不同响应格式
        items = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(items, list):
            return items[:3]
        if isinstance(items, dict) and "items" in items:
            return items["items"][:3]
        return []
    except Exception:
        return []


@router.get("/{patient_id}/care-view")
async def patient_care_view(
    patient_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> UnifiedResponse[PatientCareViewResponse]:
    """阶段 0: 患者照护视图聚合端点。

    患者/家属输入 patient_id 即可查看完整照护信息：
    - 患者基本信息（脱敏姓名、年龄、出院去向）
    - 照护计划列表（title、category、status、period）
    - 知识材料引用（来自 knowledge-orchestrator，取前 3 条）

    Args:
        patient_id: 患者业务 ID。

    Returns:
        UnifiedResponse[PatientCareViewResponse]: 聚合后的照护视图。

    Raises:
        HTTPException 404: 患者不存在。
    """
    request_id = _get_request_id(request)

    # 1. 查患者信息
    result = await session.execute(
        select(Patient).where(Patient.patient_id == patient_id)
    )
    patient = result.scalar_one_or_none()

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PATIENT_NOT_FOUND",
                "message": f"患者不存在: {patient_id}",
                "details": {"patient_id": patient_id},
            },
        )

    # 查出院去向（取最近一次就诊记录）
    enc_result = await session.execute(
        select(Encounter)
        .where(Encounter.patient_id == patient_id)
        .order_by(Encounter.end_date.desc())
        .limit(1)
    )
    encounter = enc_result.scalar_one_or_none()

    # 2. 查照护计划列表 (CarePlan)
    cp_result = await session.execute(
        select(CarePlan).where(CarePlan.patient_id == patient_id)
    )
    care_plans = cp_result.scalars().all()

    # 3. 调 knowledge-orchestrator 获取相关药物知识（两个并发请求）
    education: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            # 阶段 0: 患者照护视图聚合 —— 知识搜索关键词："用药指导" + "出院注意事项"
            med_results, discharge_results = await asyncio.gather(
                _search_knowledge(http_client, "用药指导"),
                _search_knowledge(http_client, "出院注意事项"),
            )

            # 合并去重，取前 3 条
            seen_titles: set[str] = set()
            for item in med_results + discharge_results:
                title = item.get("title", "")
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    education.append({
                        "title": title,
                        "text": item.get("text", item.get("content", "")),
                        "source": item.get("source", "knowledge-orchestrator"),
                    })
            education = education[:3]
    except Exception:
        # 知识检索失败时 education 返回空列表，不阻断主流程
        education = []

    # 4. 组装返回: {patient, care_plans, education: [知识片段]}
    patient_info: dict = {
        "name": patient.name,
        "gender": patient.gender,
        "age": _calc_age(patient.birth_date),
        "discharge_to": encounter.discharge_to if encounter else None,
    }

    care_plan_list: list[dict] = []
    for cp in care_plans:
        # title 优先使用模型字段，否则根据 category 推导
        cp_title = cp.title or (
            "出院随访计划" if cp.category == "discharge" else "慢病随访计划"
        )
        care_plan_list.append({
            "title": cp_title,
            "category": cp.category,
            "status": cp.status,
            "period": {
                "start": cp.period_start.isoformat() if cp.period_start else None,
                "end": cp.period_end.isoformat() if cp.period_end else None,
            },
        })

    response_data = PatientCareViewResponse(
        patient=patient_info,
        care_plans=care_plan_list,
        education=education,
    )
    return UnifiedResponse(request_id=request_id, data=response_data, error=None)
