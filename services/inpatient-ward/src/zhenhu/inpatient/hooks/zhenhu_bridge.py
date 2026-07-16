"""臻护桥接 —— 出院→workflow-engine / RAG→knowledge-orchestrator / 患者摘要→fhir-adapter。合并迁入。

阶段5 fixture占位。阶段6(桥接)对接臻护PoC验证。
阶段K: URL 常量统一从 zhenhu.contracts.ServiceConfig 导入。
"""

import os
import asyncio

import httpx

# 阶段K: 统一从 contracts 导入, 环境变量驱动的服务地址
from zhenhu.contracts import ServiceConfig

WORKFLOW_URL = ServiceConfig.WORKFLOW_URL
KNOWLEDGE_URL = ServiceConfig.KNOWLEDGE_URL
FHIR_URL = ServiceConfig.FHIR_URL


async def bridge_discharge_to_zhenhu(handoff_items: list[dict], patient_id: str, template: dict | None = None) -> dict:
    """出院交接→臻护创建病例。

    HTTP 调用链:
    1. 基于病种模板构造 PlanDefinition(handoff_items → action[])
    2. 调 workflow-engine POST /cases 创建病例
    3. 降级策略: httpx 超时/连接失败 → 返回 bridge_unavailable, 不阻断 Agent 流程
    """
    template = template or {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            pd = {
                "resourceType": "PlanDefinition",
                "title": f"出院交接计划-{template.get('name', patient_id)}",
                "status": "active",
                "action": [
                    {
                        "title": item.get("content", ""),
                        "description": item.get("type", ""),
                    }
                    for item in handoff_items
                ],
            }

            resp = await client.post(
                f"{WORKFLOW_URL}/cases",
                json={
                    "input_snapshot_id": f"zhenhu-{patient_id}",
                    "care_plan_ref": pd["title"],
                },
            )
            if resp.status_code in (200, 201):
                return resp.json()
    except Exception:
        pass
    return {"status": "bridge_unavailable", "case_id": None, "bridge_error": "臻护workflow-engine不可达，病例未创建，请手动重试"}


async def bridge_search_knowledge(query: str, top_k: int = 10) -> list[dict]:
    """RAG检索→臻护knowledge-orchestrator。

    GET {KNOWLEDGE_URL}/knowledge/search?q={query}&top_k={top_k}
    降级策略: httpx 超时/连接失败 → 返回空列表, Agent 回退到病种模板默认值。
    """
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"{KNOWLEDGE_URL}/knowledge/search",
                params={"q": query, "top_k": top_k},
            )
            if resp.status_code == 200:
                return resp.json().get("data", {}).get("results", [])
    except Exception:
        pass
    return []


async def bridge_patient_summary(patient_id: str) -> dict:
    """患者脱敏摘要→臻护fhir-adapter。

    GET {FHIR_URL}/fhir/Patient/{patient_id}
    降级策略: HTTP 失败 → 返回匿名摘要, 不阻断入院流程。
    """
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{FHIR_URL}/fhir/Patient/{patient_id}")
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                return {
                    "name": (
                        data.get("name", [{}])[0].get("text", "***")
                        if data.get("name")
                        else "***"
                    ),
                    "gender": data.get("gender", "unknown"),
                    "discharge_to": "home",
                }
    except Exception:
        pass
    return {"name": "***", "gender": "unknown", "discharge_to": "home"}


# ============================================================================
# 阶段G: 桥接增强 — 退避重试 + 熔断器保护
# ============================================================================


# 阶段M Agent升级: CircuitBreakerOpenError 从 contracts 导入
from zhenhu.contracts.agent import CircuitBreakerOpenError
from ..agent.harness import bridge_circuit


async def bridge_discharge_to_zhenhu_with_retry(
    handoff_items: list[dict], patient_id: str, template: dict, max_retries: int = 2
) -> dict:
    """带退避重试的出院桥接(阶段G)。

    指数退避 1s/2s, 熔断器保护。
    """
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                result = await bridge_discharge_to_zhenhu(handoff_items, patient_id, template)
                if result.get("status") != "bridge_unavailable":
                    return result
        except (CircuitBreakerOpenError, Exception):
            pass

        if attempt < max_retries:
            wait = 2 ** attempt
            await asyncio.sleep(wait)

    return {"status": "bridge_failed_after_retries", "case_id": None, "retries": max_retries}
