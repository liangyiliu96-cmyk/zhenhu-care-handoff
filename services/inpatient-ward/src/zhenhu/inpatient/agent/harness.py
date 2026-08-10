"""Agent Harness 安全护栏 —— 输出校验 + 幻觉检测 + 回退策略。

阶段M Agent升级: CircuitBreaker/AgentAuditHook/CircuitBreakerOpenError 从 contracts 导入，
住院特定校验函数保留在此。
"""

import math
import os
from typing import Any, Literal

from pydantic import BaseModel, Field

# 阶段M: 从 contracts 导入共享基础架构
from zhenhu.contracts.agent import (
    CircuitBreaker,
    CircuitBreakerOpenError,  # noqa: F401 — 对外再导出 (tests 经本模块导入)
    AgentAuditHook,  # noqa: F401 — 对外再导出 (tests 经本模块导入)
)


class HandoffItemSchema(BaseModel):
    """交接事项必须满足的schema。"""

    type: Literal["medication", "monitoring", "followup"] = Field(
        ..., description="事项类型: medication|monitoring|followup"
    )
    content: str = Field(..., min_length=5, description="事项内容")
    feedback: str | None = None


class DifferentialDiagnosisSchema(BaseModel):
    """Minimum contract for an LLM-suggested differential diagnosis."""

    diagnosis: str = Field(..., min_length=2, max_length=120)
    likelihood: Literal["high", "moderate", "low"]
    icd10: str = Field(default="", max_length=16)
    rationale: str | None = Field(default=None, max_length=500)


class MedicationAdjustmentSchema(BaseModel):
    """Minimum contract for a draft medication adjustment.

    This validates a draft only. The existing doctor-review checkpoint remains
    the sole authorization path for any medication change.
    """

    drug_name: str = Field(..., min_length=1, max_length=120)
    action: Literal["start", "stop", "hold", "adjust", "monitor"]
    rationale: str = Field(..., min_length=5, max_length=500)
    suggested_dose: str | None = Field(default=None, max_length=120)
    requires_doctor_confirmation: bool = True


def validate_handoff_items(items: list[dict] | None) -> tuple[list[dict], list[str]]:
    """校验交接事项。返回(有效项, 错误列表)。

    阶段H审计修复: 防御 None 输入。
    """
    if items is None:
        return [], []
    if not isinstance(items, list):
        return [], ["handoff_items: expected a list"]
    valid, errors = [], []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"handoff_item[{i}]: expected an object")
            continue
        try:
            HandoffItemSchema(**item)
            valid.append(item)
        except Exception as e:
            errors.append(f"handoff_item[{i}]: {e}")
    return valid, errors


def validate_llm_output(
    kind: Literal["handoff", "ddx", "medication_adjustment"], payload: Any,
) -> tuple[list[dict], list[str]]:
    """Validate model output before it can enter a clinical draft.

    Invalid items are rejected individually, preserving deterministic/template
    draft items and allowing the existing review gates to continue operating.
    """
    schema_map = {
        "handoff": HandoffItemSchema,
        "ddx": DifferentialDiagnosisSchema,
        "medication_adjustment": MedicationAdjustmentSchema,
    }
    if not isinstance(payload, list):
        return [], [f"{kind}: expected a list"]

    schema = schema_map[kind]
    valid: list[dict] = []
    errors: list[str] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            errors.append(f"{kind}[{index}]: expected an object")
            continue
        try:
            model = schema(**item)
            valid.append(model.model_dump(exclude_none=True))
        except Exception as exc:
            errors.append(f"{kind}[{index}]: {exc}")
    return valid, errors


def _evidence_min_score() -> float:
    """Return a bounded retrieval score threshold without weakening defaults."""
    try:
        configured = float(os.getenv("RAG_EVIDENCE_MIN_SCORE", "0.6"))
    except ValueError:
        configured = 0.6
    return min(max(configured, 0.0), 1.0)


def check_source_type(knowledge_results: list[dict], threshold: float | None = None) -> dict:
    """基于检索评分判断溯源类型。

    score >= threshold → source_knowledge
    score < threshold  → source_none(幻觉标记, 不得入草稿)
    无结果            → source_none
    """
    threshold = _evidence_min_score() if threshold is None else threshold
    if not isinstance(knowledge_results, list) or not knowledge_results:
        return {"source_type": "source_none", "count": 0}
    high_quality = []
    for result in knowledge_results:
        if not isinstance(result, dict):
            continue
        try:
            score = float(result.get("score", 0))
        except (TypeError, ValueError):
            continue
        if math.isfinite(score) and score >= threshold:
            high_quality.append(result)
    if high_quality:
        return {"source_type": "source_knowledge", "count": len(high_quality)}
    return {"source_type": "source_none", "count": 0}


def fallback_to_template(template: dict) -> dict:
    """RAG检索失败→回退到病种模板默认值。"""
    instructions = template.get("handoff_instructions", []) if isinstance(template, dict) else []
    if not isinstance(instructions, list):
        instructions = []
    candidates = [
        {
            "type": instruction.get("type", "unknown"),
            "content": instruction.get("content", ""),
            "source": "disease_template_fallback",
        }
        for instruction in instructions
        if isinstance(instruction, dict)
    ]
    valid, _ = validate_handoff_items(candidates)
    return {
        "handoff_items": valid,
        "source_type": "source_none",
    }


def normalize_template(template: dict) -> dict:
    """标准化模板字段名，确保兼容性。
    
    将旧命名(key/alert_high/alert_low)统一为(name/alert_above/alert_below)。
    即使模板已用新字段名，该函数也是空操作。
    """
    vs = template.get("vital_signs", [])
    for v in vs:
        if "key" in v and "name" not in v:
            v["name"] = v.pop("key")
        if "alert_high" in v and "alert_above" not in v:
            v["alert_above"] = v.pop("alert_high")
        if "alert_low" in v and "alert_below" not in v:
            v["alert_below"] = v.pop("alert_low")
    return template


# 全局熔断器实例(阶段G) — 阶段M: 类型从 contracts 导入
bridge_circuit = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)


# ═══════════════════════════════════════════════════════════
# 多病共存合并 — 从多模板合并监测规则
# ═══════════════════════════════════════════════════════════

def merge_comorbidity_template(primary_template: dict,
                                comorbidity_ids: list[str]) -> dict:
    """将合并症的 complication_monitoring/vital_signs/lab/禁忌合并到主模板。

    合并策略:
    - complication_monitoring: 按 complication 名去重合并，watch 列表取并集
    - vital_signs: 同名体征取最严阈值(alert_above 取最小, alert_below 取最大)
    - lab_reference: 同名检验取最严范围(low取最大, high取最小)
    - contraindications: 取并集

    Args:
        primary_template: 主病种模板
        comorbidity_ids: 合并症 disease_id 列表(如 ["diabetes", "hypertension"])

    Returns:
        合并后的模板 dict (深拷贝,不修改原对象)
    """
    import copy
    from .nodes_admission import load_template

    if not comorbidity_ids:
        return copy.deepcopy(primary_template)

    merged = copy.deepcopy(primary_template)
    loaded: list[dict] = []
    for cid in comorbidity_ids:
        try:
            loaded.append(load_template(cid))
        except FileNotFoundError:
            pass

    if not loaded:
        return merged

    # ── 1. complication_monitoring: 按 complication 名合并 ──
    seen = {c["complication"]: c for c in merged.get("complication_monitoring", [])}
    for tpl in loaded:
        for entry in tpl.get("complication_monitoring", []):
            name = entry.get("complication", "")
            if name in seen:
                existing_watch = {w for w in seen[name].get("watch", [])}
                new_watches = [w for w in entry.get("watch", []) if w not in existing_watch]
                seen[name]["watch"] = seen[name].get("watch", []) + new_watches
            else:
                seen[name] = copy.deepcopy(entry)
    merged["complication_monitoring"] = list(seen.values())

    # ── 2. vital_signs: 同名体征取最严阈值 ──
    vs_map: dict[str, dict] = {}
    for v in merged.get("vital_signs", []):
        vs_map[v["name"]] = v
    for tpl in loaded:
        for v in tpl.get("vital_signs", []):
            name = v.get("name", "")
            if not name:
                continue
            if name in vs_map:
                existing = vs_map[name]
                existing["alert_above"] = _min_alert(existing.get("alert_above"), v.get("alert_above"))
                existing["alert_below"] = _max_alert(existing.get("alert_below"), v.get("alert_below"))
            else:
                vs_map[name] = copy.deepcopy(v)
    merged["vital_signs"] = list(vs_map.values())

    # ── 3. lab_reference: 同名检验取最严范围 ──
    merged_lab = dict(merged.get("lab_reference", {}))
    for tpl in loaded:
        for lab_name, ref in (tpl.get("lab_reference") or {}).items():
            if lab_name in merged_lab:
                merged_lab[lab_name] = {
                    "low": max(merged_lab[lab_name].get("low", -float("inf")),
                               ref.get("low", -float("inf"))),
                    "high": min(merged_lab[lab_name].get("high", float("inf")),
                                ref.get("high", float("inf"))),
                }
            else:
                merged_lab[lab_name] = dict(ref)
    merged["lab_reference"] = merged_lab

    # ── 4. contraindications: 取并集 ──
    merged_ci = set(merged.get("contraindications", []))
    for tpl in loaded:
        merged_ci.update(tpl.get("contraindications", []))
    merged["contraindications"] = list(merged_ci)

    return merged


def _min_alert(a, b):
    """取最严 alert_above: 更小的值(更容易触发警报)"""
    if a is None:
        return b
    if b is None:
        return a
    try:
        return min(float(a), float(b))
    except (ValueError, TypeError):
        return a


def _max_alert(a, b):
    """取最严 alert_below: 更大的值(更容易触发警报)"""
    if a is None:
        return b
    if b is None:
        return a
    try:
        return max(float(a), float(b))
    except (ValueError, TypeError):
        return a


# ═══════════════════════════════════════════════════════════
# 模板质量校验
# ═══════════════════════════════════════════════════════════

_REQUIRED_TEMPLATE_FIELDS = [
    "disease_id", "name", "department", "vital_signs",
    "discharge_criteria", "handoff_instructions", "complication_monitoring",
    "lab_reference",
]


def validate_template(template: dict) -> list[str]:
    """校验模板必需字段 + department 非空。

    Returns:
        缺失/问题描述列表，空列表表示模板完整。
    """
    if template is None:
        return ["模板为 None"]
    issues = []
    for field in _REQUIRED_TEMPLATE_FIELDS:
        if field not in template:
            issues.append(f"缺少字段: {field}")
        elif field == "department" and not template[field]:
            issues.append("department 为空")
    return issues


def detect_department_mismatch(primary_dept: str, comorbidity_ids: list[str]) -> list[str]:
    """检测跨科室不匹配 — 合并症是否来自其他科室。

    返回警告消息列表（不阻断流程），供 clinical_alerts 使用。
    """
    from .nodes_admission import load_template

    warnings = []
    for cid in comorbidity_ids:
        try:
            tpl = load_template(cid)
            c_dept = tpl.get("department", "")
            if c_dept and c_dept != primary_dept:
                warnings.append(
                    f"[多科室] 合并症 {tpl.get('name', cid)}({c_dept}) 与主科室({primary_dept})不同，建议会诊"
                )
        except Exception:
            pass
    return warnings




# ═══════════════════════════════════════════════════════════
# ##2 出院小结完整性 QA
# ═══════════════════════════════════════════════════════════

def validate_discharge_summary(summary_text: str,
                                discharge_criteria: list[dict]) -> dict:
    """检查出院小结是否覆盖了出院标准的各项条件。

    Returns:
        {"coverage": 0.0-1.0, "missing": [...], "covered": [...]}
    """
    if not summary_text or not discharge_criteria:
        return {"coverage": 0.0, "missing": [], "covered": []}

    covered = []
    missing = []
    normalized_summary = summary_text.lower()
    for c in discharge_criteria:
        desc = c.get("description", c.get("condition", ""))
        keywords = c.get("condition", desc).lower().split("_")
        # 简单但有效的检测：描述或关键字段是否在摘要中出现
        hit = bool(desc and desc.lower() in normalized_summary) or any(
            kw in normalized_summary for kw in keywords if len(kw) > 1
        )
        if hit:
            covered.append(desc)
        else:
            missing.append(desc)

    total = len(discharge_criteria)
    coverage = len(covered) / max(total, 1)
    return {"coverage": round(coverage, 2), "missing": missing, "covered": covered}


def compute_readiness_score(state: dict) -> dict:
    """出院准备度评分: 0-100，100=完全准备好。共享于 dashboard + CDS Hooks。"""
    score = 100.0
    deductions = []
    dc = state.get("discharge_criteria_check") or {}
    if not dc.get("all_met"):
        unmet = len(dc.get("unmet", []))
        if unmet > 0:
            d = min(unmet * 15, 50); score -= d
            deductions.append(f"出院标准未达标({unmet}项): -{d}")
    news2 = state.get("news2_score")
    if news2 is not None:
        if news2 >= 7: score -= 30; deductions.append(f"NEWS2={news2}: -30")
        elif news2 >= 5: score -= 15; deductions.append(f"NEWS2={news2}: -15")
    if not state.get("handoff_acknowledged"):
        score -= 10; deductions.append("交接未确认: -10")
    alerts = len(state.get("clinical_alerts", []) or [])
    if alerts >= 3: score -= 10; deductions.append(f"活跃告警{alerts}条: -10")
    score = max(0, round(score, 1))
    status = "🟢 可出院" if score >= 85 else ("🟡 准备中" if score >= 60 else "🔴 不建议")
    return {"score": score, "status": status, "deductions": deductions}
