"""Agent 临床节点 —— v1.3 §六 Batch A+B 基础建设。
P1-4 拆分: LLM 工具层 → llm_utils.py, 三卡点 → nodes_checkpoints.py。

保留: node_history_taking（病史采集）、node_physical_exam（体格检查）、
node_ddx（鉴别诊断）、node_nursing（护理记录）、node_shift_summary（交班摘要）。
全部节点均含幂等守卫，LLM 调用包 try/except 不阻断流程。
"""

import asyncio
import json
import logging

from pydantic import ValidationError

from .config import get_cached_provider  # P1-2
from .llm_utils import safe_llm_invoke, deep_invoke, get_provider_for_node, cache_get, cache_set, cache_key as _ckey, DDxItem  # P1-4 + v0.3
from .harness import validate_llm_output
from . import prompts  # P1-1
from .metrics import record
from ..services.clinical_evidence import merge_rag_citations

logger = logging.getLogger("zhenhu.inpatient")


async def node_history_taking(state: dict) -> dict:
    """病史采集节点 — v1.3 §六 6.1。

    遵循 SOAP/OLDCARTS 框架，采集 CC + HPI + PMH + FH + SH + ROS。
    幂等守卫：if state.get("history_data"): return {}（陷阱①修复）。
    LLM 失败不阻断流程，返回空结构 + insufficient_data flag。
    HPI + ROS 并发执行（asyncio.gather），任一失败不阻塞另一。
    """
    # ── 幂等守卫（陷阱①修复）──
    if state.get("history_data"):
        return {}

    patient_id = state.get("patient_id", "unknown")
    logger.info("node_history_taking: start, patient=%s", patient_id)

    # ── 从模板取配置 ──
    template = state.get("disease_template", {})
    ht = template.get("history_template", {})

    # ── 取患者已有数据 ──
    patient_data = state.get("patient_data", {})
    chief_complaint = patient_data.get("chief_complaint", "")
    existing_history = state.get("patient_history", {}) or {}
    allergies = state.get("allergies", []) or []

    hpi_focus = ht.get("hpi_focus", [])
    ros_systems = ht.get("ros_focus_systems", [])

    # ── HPI + ROS 并发 ──

    async def _generate_hpi() -> str | None:
        cc_text = chief_complaint or "未提供主诉"
        pmh_text = json.dumps(existing_history.get("pmh", {}), ensure_ascii=False) if isinstance(existing_history, dict) else "{}"
        hpi_prompt = prompts.hpi_prompt(cc_text, hpi_focus, pmh_text)
        cache_key = _ckey(patient_id, "hpi", {
            "chief_complaint": chief_complaint,
            "hpi_focus": hpi_focus,
            "pmh_text": pmh_text,
        })
        cached_result = cache_get(cache_key)
        if cached_result:
            logger.info("node_history_taking: HPI cache hit, patient=%s", patient_id)
            return cached_result.get("hpi_narrative")

        ai_provider = get_cached_provider()
        llm_result = await safe_llm_invoke(
            ai_provider, hpi_prompt,
            context={"disease_template": template, "patient_data": patient_data},
            timeout=10.0,
        )
        if llm_result and llm_result.get("source_type") != "source_none":
            raw = llm_result.get("response") or llm_result.get("hpi_narrative", "")
            try:
                parsed = json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("{") else {}
                result = parsed.get("hpi_narrative") or (raw if isinstance(raw, str) else raw.get("hpi_narrative", ""))
            except (json.JSONDecodeError, ValueError):
                result = raw if isinstance(raw, str) else raw.get("hpi_narrative", "")
            cache_set(cache_key, llm_result)
            return result
        return None

    async def _generate_ros() -> dict | None:
        ros_prompt = prompts.ros_prompt(chief_complaint or "未提供", ros_systems)
        cache_key = _ckey(patient_id, "ros", {
            "chief_complaint": chief_complaint,
            "ros_systems": ros_systems,
        })
        cached_result = cache_get(cache_key)
        if cached_result:
            logger.info("node_history_taking: ROS cache hit, patient=%s", patient_id)
            return cached_result.get("ros_findings") or cached_result.get("response", None)

        ai_provider = get_cached_provider()
        llm_result = await safe_llm_invoke(
            ai_provider, ros_prompt,
            context={"disease_template": template, "patient_data": patient_data},
            timeout=10.0,
        )
        if llm_result and llm_result.get("source_type") != "source_none":
            result = llm_result.get("ros_findings") or llm_result.get("response", None)
            cache_set(cache_key, llm_result)
            return result
        return None

    hpi_result, ros_result = await asyncio.gather(_generate_hpi(), _generate_ros(), return_exceptions=True)

    hpi_narrative = None
    if isinstance(hpi_result, Exception):
        logger.warning("node_history_taking: HPI coroutine raised exception, patient=%s: %s", patient_id, hpi_result)
    elif hpi_result is not None:
        hpi_narrative = hpi_result

    ros_findings = None
    if isinstance(ros_result, Exception):
        logger.warning("node_history_taking: ROS coroutine raised exception, patient=%s: %s", patient_id, ros_result)
    elif ros_result is not None:
        ros_findings = ros_result

    # ── 组装病史数据 ──
    pmh = existing_history.get("pmh", {}) if isinstance(existing_history, dict) else {}
    fh = existing_history.get("fh", {}) if isinstance(existing_history, dict) else {}
    sh = existing_history.get("sh", {}) if isinstance(existing_history, dict) else {}

    history_data = {
        "chief_complaint": chief_complaint,
        "hpi_narrative": hpi_narrative,
        "ros_findings": ros_findings,
        "allergies": allergies,
        "pmh": pmh,
        "fh": fh,
        "sh": sh,
        "insufficient_data": hpi_narrative is None,
    }

    record("history_taking")
    return {
        "history_data": history_data,
        "hpi_narrative": hpi_narrative,
        "ros_findings": ros_findings,
        "document_chain": state.get("document_chain", []) + ["history_note"],
    }


async def node_physical_exam(state: dict) -> dict:
    """体格检查节点 — v1.3 §六 6.2。

    遵循 Bates 体格检查指南/中国体格检查规范，根据 pe_template 定制检查项目。
    幂等守卫：if state.get("pe_data"): return {}（陷阱①修复）。
    LLM 失败不阻断流程，返回空结构 + insufficient_data flag。
    """
    # ── 幂等守卫（陷阱①修复）──
    if state.get("pe_data"):
        return {}

    patient_id = state.get("patient_id", "unknown")
    logger.info("node_physical_exam: start, patient=%s", patient_id)

    # ── 从模板取配置 ──
    template = state.get("disease_template", {})
    pet = template.get("pe_template", {})

    required_systems = pet.get("required_systems", [])
    focus_items = pet.get("focus_items", [])

    # ── 取已有数据 ──
    vital_signs = state.get("vital_signs", [])
    latest_vs = vital_signs[-1] if vital_signs else {}
    history_data = state.get("history_data") or {}
    chief_complaint = history_data.get("chief_complaint", "")
    hpi_narrative = state.get("hpi_narrative") or ""

    # ── LLM 生成体格检查叙事 ──
    pe_narrative = None
    vs_text = json.dumps(latest_vs, ensure_ascii=False) if latest_vs else "无生命体征数据"
    cache_key = _ckey(patient_id, "pe", {
        "chief_complaint": chief_complaint,
        "hpi_narrative": hpi_narrative,
        "required_systems": required_systems,
        "focus_items": focus_items,
        "latest_vs": latest_vs,
    })
    cached_result = cache_get(cache_key)
    if cached_result:
        logger.info("node_physical_exam: PE cache hit, patient=%s", patient_id)
        pe_narrative = cached_result.get("pe_narrative") or cached_result.get("response", "")
    else:
        ai_provider = get_cached_provider()
        pe_prompt = prompts.pe_prompt(chief_complaint, hpi_narrative, vs_text,
                                       required_systems, focus_items)
        llm_result = await safe_llm_invoke(
            ai_provider, pe_prompt,
            context={
                "disease_template": template,
                "vital_signs": latest_vs,
                "history_data": history_data,
            },
            timeout=10.0,
        )
        if llm_result and llm_result.get("source_type") != "source_none":
            raw = llm_result.get("response") or llm_result.get("pe_narrative", "")
            try:
                parsed = json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("{") else {}
                pe_narrative = parsed.get("pe_narrative") or (raw if isinstance(raw, str) else raw.get("pe_narrative", ""))
            except (json.JSONDecodeError, ValueError):
                pe_narrative = raw if isinstance(raw, str) else raw.get("pe_narrative", "")
            cache_set(cache_key, llm_result)

    # ── 组装体格检查数据 ──
    pe_data = {
        "vital_signs": latest_vs,
        "required_systems": required_systems,
        "focus_items": focus_items,
        "pe_narrative": pe_narrative,
        "insufficient_data": pe_narrative is None,
    }

    record("physical_exam")
    return {
        "pe_data": pe_data,
        "pe_narrative": pe_narrative,
        "document_chain": state.get("document_chain", []) + ["pe_note"],
    }


# ═══════════════════════════════════════════════════════════════
# Batch B: 流程扩展节点
# ═══════════════════════════════════════════════════════════════


async def node_ddx(state: dict) -> dict:
    """鉴别诊断节点 — v1.3 §六 6.3。

    基于 CC + HPI narrative + PE narrative 生成 TOP 3-5 鉴别诊断。
    幂等守卫：if state.get("ddx_list"): return {}（陷阱①修复）。
    LLM 失败降级：ddx_unavailable=True, ddx_list=[]。
    DDx 输出经 Pydantic schema 校验，最多重试 3 次。
    """
    # ── 幂等守卫（陷阱①修复 + v1.1 P1a DDx sentinel）──
    if state.get("ddx_list") or state.get("ddx_reviewed"):
        return {}

    patient_id = state.get("patient_id", "unknown")
    logger.info("node_ddx: start, patient=%s", patient_id)

    # ── 取输入数据 ──
    template = state.get("disease_template", {})
    current_disease_name = template.get("name") or template.get("disease_id", "unknown")
    history_data = state.get("history_data") or {}
    chief_complaint = history_data.get("chief_complaint", "")
    hpi_narrative = state.get("hpi_narrative") or ""
    pe_data = state.get("pe_data") or {}
    pe_narrative = pe_data.get("pe_narrative") or ""
    allergies = state.get("allergies", []) or []
    lab_results = state.get("lab_results", []) or []
    patient_history = state.get("patient_history", {}) or {}
    comorbidities = patient_history.get("comorbidities") or list((patient_history.get("pmh") or {}).keys())

    ddx_list = None
    ddx_unavailable = False
    evidence_citations = []

    cache_key = _ckey(patient_id, "ddx", {
        "chief_complaint": chief_complaint,
        "hpi_narrative": hpi_narrative,
        "pe_narrative": pe_narrative,
        "disease_name": current_disease_name,
        "allergies": allergies,
        "lab_results": lab_results[-3:] if lab_results else [],
        "comorbidities": comorbidities,
    })
    cached_result = cache_get(cache_key)
    if cached_result:
        logger.info("node_ddx: DDx cache hit, patient=%s", patient_id)
        ddx_list = cached_result.get("ddx_list", [])
    else:
        ai_provider = get_cached_provider()
        allergies_text = json.dumps(allergies, ensure_ascii=False)
        labs_text = json.dumps(lab_results[-3:] if lab_results else [], ensure_ascii=False)
        comorbidities_text = json.dumps(comorbidities, ensure_ascii=False)[:200] if comorbidities else "无"
        ddx_prompt = prompts.ddx_prompt(
            chief_complaint or "", hpi_narrative or "", pe_narrative or "",
            allergies_text, labs_text, comorbidities_text, current_disease_name
        )

        for attempt in range(3):
            try:
                llm_result = await deep_invoke(  # v0.3: DeepAgent 管线 (Collect→Execute→Refine)
                    ai_provider, ddx_prompt,
                    rag_query=f"{chief_complaint or ''} {current_disease_name} 鉴别诊断",
                    context={
                        "disease_template": template,
                        "chief_complaint": chief_complaint,
                        "hpi_narrative": hpi_narrative,
                        "pe_narrative": pe_narrative,
                    },
                    caller="ddx",
                    timeout=None,
                    validate_fields=["diagnosis"],
                )
                if not llm_result or llm_result.get("source_type") == "source_none":
                    raise ValueError("LLM returned empty or none response")

                raw = llm_result.get("ddx_list", [])
                if not isinstance(raw, list) or len(raw) == 0:
                    raise ValueError("ddx_list is empty or not a list")

                ddx_list = [DDxItem(**item).model_dump() for item in raw]
                evidence_citations = list(llm_result.get("_rag_citations", []) or [])

                # ── #6: 第二轮 LLM 审阅辩论 (走 Pro 强推理) ──
                try:
                    reviewer_provider = get_provider_for_node("ddx")
                    reviewer_prompt = prompts.ddx_reviewer_prompt(ddx_list)
                    reviewer_result = await safe_llm_invoke(
                        reviewer_provider, reviewer_prompt,
                        timeout=None, retries=1,
                    )
                    if reviewer_result:
                        raw_review = reviewer_result.get("response") or ""
                        if isinstance(raw_review, str) and raw_review.strip().startswith("{"):
                            review = json.loads(raw_review)
                        else:
                            review = reviewer_result
                        if isinstance(review, dict) and review.get("suggested_additions"):
                            additions, errors = validate_llm_output(
                                "ddx", review["suggested_additions"]
                            )
                            if errors:
                                logger.info("node_ddx: rejected %d invalid reviewer additions", len(errors))
                            if additions:
                                ddx_list.extend(additions)
                except Exception:
                    pass  # 审阅失败不影响第一轮 DDx

                cache_set(cache_key, llm_result)
                break
            except (ValidationError, TypeError, ValueError) as e:
                if attempt == 2:
                    logger.warning("node_ddx: DDx validation failed after 3 attempts: %s, patient=%s", e, patient_id)
                    ddx_list = []
                    ddx_unavailable = True
                else:
                    logger.info("node_ddx: DDx validation retry %d/3, patient=%s", attempt + 1, patient_id)
                    ddx_prompt += "\n\n请确保返回的JSON严格符合上述schema格式，每个diagnosis对象必须包含diagnosis/icd10/likelihood/key_findings/rationale字段。"

    # ── 降级处理 ──
    if not ddx_list and not ddx_unavailable:
        logger.info("node_ddx: fallback, marking ddx_unavailable, patient=%s", patient_id)
        ddx_list = []
        ddx_unavailable = True
    elif ddx_list and not ddx_unavailable:
        ddx_unavailable = False

    existing_evidence = list(state.get("clinical_evidence", []) or [])
    existing_ids = {item.get("citation_id") for item in existing_evidence if isinstance(item, dict)}
    for citation in evidence_citations:
        if isinstance(citation, dict) and citation.get("citation_id") not in existing_ids:
            existing_evidence.append(citation)
            existing_ids.add(citation["citation_id"])

    record("ddx")
    return {
        "ddx_list": ddx_list,
        "ddx_unavailable": ddx_unavailable,
        "clinical_evidence": existing_evidence[-20:],
        "document_chain": state.get("document_chain", []) + ["ddx_note"],
    }


async def node_nursing(state: dict) -> dict:
    """护理记录节点 — v1.3 §六 6.4。

    基于 vital_signs + medication_adjustments 生成护理记录（MAR + I/O + 护理措施）。
    每个查房轮次最多生成一条 Agent 护理记录。
    LLM 失败不阻断，返回空记录。
    """
    round_count = int(state.get("round_count", 0))
    if state.get("nursing_last_round") == round_count:
        return {}

    patient_id = state.get("patient_id", "unknown")
    logger.info("node_nursing: start, patient=%s", patient_id)

    # ── 取输入数据 ──
    vital_signs = state.get("vital_signs", [])
    latest_vs = vital_signs[-1] if vital_signs else {}
    medication_adjustments = state.get("medication_adjustments", []) or []
    template = state.get("disease_template", {})

    # ── 构建给药记录 ──
    medications_administered = []
    for adj in medication_adjustments[-3:]:  # 最近 3 条调药记录
        med = {
            "drug": adj.get("drug", adj.get("name", "unknown")),
            "dose": adj.get("dose", adj.get("suggested_dose", "")),
            "route": adj.get("route", "PO"),
            "time": adj.get("time", ""),
        }
        medications_administered.append(med)

    nursing_alerts = []
    nursing_actions = "按病种常规护理"
    evidence_citations: list[dict] = []

    ##4 科室级护理清单
    dept = template.get("department", "")
    if dept:
        from .constants import get_dept_checklist
        checklist = get_dept_checklist(dept)
        if checklist:
            nursing_actions = "; ".join(checklist) + " | " + nursing_actions

    # ── LLM 补充护理措施 ──
    disease_name = template.get("name") or template.get("disease_id", "unknown")
    cache_key = _ckey(patient_id, "nursing", {
        "disease_name": disease_name,
        "latest_vs": latest_vs,
        "medications_administered": medications_administered,
    })
    cached_result = cache_get(cache_key)
    if cached_result:
        logger.info("node_nursing: nursing cache hit, patient=%s", patient_id)
        nursing_actions = cached_result.get("nursing_actions", nursing_actions)
        alerts = cached_result.get("alerts")
        if isinstance(alerts, list):
            nursing_alerts = alerts
        evidence_citations = list(cached_result.get("_rag_citations", []) or [])
    else:
        # ── LLM 减量: 体征稳定 + checklist已全 → 不调用LLM ──
        need_llm = False
        latest_alerts = nursing_alerts or []
        # 只有出现新告警或无checklist时触发LLM增强
        if nursing_alerts or not dept:
            need_llm = True
        if latest_vs.get("spo2", 100) < 92 or latest_vs.get("heart_rate", 80) > 100:
            need_llm = True

        if need_llm:
            ai_provider = get_cached_provider()
            nursing_prompt = prompts.nursing_prompt(
                latest_vs, medications_administered, [], []
            )
            llm_result = await deep_invoke(
                ai_provider, nursing_prompt,
                rag_query=f"{disease_name} 护理措施和异常体征处理",
                context={"disease_template": template, "vital_signs": latest_vs},
                caller="nursing",
                timeout=10.0,
            )
            if llm_result and llm_result.get("source_type") != "source_none":
                nursing_actions = llm_result.get("nursing_actions", nursing_actions)
                alerts = llm_result.get("alerts")
                if isinstance(alerts, list):
                    nursing_alerts = alerts
                evidence_citations = list(llm_result.get("_rag_citations", []) or [])
                cache_set(cache_key, llm_result)

    nursing_record = {
        "timestamp": latest_vs.get("timestamp", ""),
        "round_number": round_count,
        "source": "agent",
        "vital_signs": latest_vs,
        "medications_administered": medications_administered,
        "intake_ml": 0,
        "output_ml": 0,
        "nursing_actions": nursing_actions,
        "alerts": nursing_alerts,
        "citations": evidence_citations,
    }

    record("nursing")
    return {
        "nursing_records": [*(state.get("nursing_records") or []), nursing_record],
        "nursing_last_round": round_count,
        "nursing_alerts": nursing_alerts,
        "clinical_evidence": merge_rag_citations(
            state.get("clinical_evidence"), evidence_citations
        ),
        "document_chain": state.get("document_chain", []) + ["nursing_note"],
    }


# ═══════════════════════════════════════════════════════════════
# #1: LLM 每日交班摘要
# ═══════════════════════════════════════════════════════════════


async def node_shift_summary(state: dict) -> dict:
    """LLM 生成交班摘要 — 每日查房后自动生成一段交班要点。

    每个查房轮次最多生成一次，历史摘要追加保存。
    依赖 daily_round_note 已存在，否则跳过。
    LLM 失败不阻断流程，返回空摘要。
    """
    patient_id = state.get("patient_id", "unknown")
    chain = state.get("document_chain", [])

    if "daily_round_note" not in chain:
        return {}

    hpi = state.get("hpi_narrative") or ""
    vs = state.get("vital_signs", []) or []
    latest = vs[-1] if vs else {}
    prev = vs[-6] if len(vs) >= 6 else (vs[0] if len(vs) > 1 else {})
    alerts = state.get("clinical_alerts", []) or []
    tpl = state.get("disease_template", {}) or {}
    round_count = state.get("round_count", 0)
    if state.get("shift_summary_last_round") == round_count:
        return {}
    news2 = state.get("news2_score")
    discharge = state.get("discharge_decision", "")
    evidence_citations: list[dict] = []

    # 趋势计算
    bp_now = f"{latest.get('systolic_mmhg','?')}/{latest.get('diastolic_mmhg','?')}"
    bp_before = f"{prev.get('systolic_mmhg','?')}/{prev.get('diastolic_mmhg','?')}" if prev else "无"
    spo2_now = latest.get("spo2", "?")
    hr_now = latest.get("heart_rate", "?")
    disease_name = tpl.get("name") or tpl.get("disease_id", "")
    alert_count = len(alerts)

    # ── Rules-first: 规则生成基础摘要 ──
    summary = (
        f"患者{disease_name}，第{round_count}轮查房。"
        f"BP {bp_now}，SpO2 {spo2_now}%，HR {hr_now}/min。"
        f"NEWS2: {news2 if news2 is not None else '未评'}，"
        f"出院决定: {discharge or '未决定'}。"
    )
    if alert_count > 0:
        top_alert = alerts[-1] if isinstance(alerts[-1], str) else str(alerts[-1])
        summary += f"已触发 {alert_count} 条临床告警，最新: {top_alert[:60]}。"
    else:
        summary += "无新发告警。"
    summary += f" 体征{'稳定' if news2 is None or news2 < 5 else '需关注'}。"

    # ── LLM 仅在复杂场景触发: 多告警 或 高危 ──
    need_llm = alert_count >= 3 or (news2 is not None and news2 >= 5)
    if need_llm:
        try:
            ai_provider = get_cached_provider()
            prompt = prompts.shift_summary_prompt(
                disease_name, round_count,
                bp_now, bp_before,
                str(spo2_now), str(hr_now),
                news2, discharge, alerts, hpi
            )
            llm_result = await deep_invoke(
                ai_provider,
                prompt,
                rag_query=f"{disease_name} 交班重点和风险处理",
                caller="shift_summary",
                timeout=30.0,
            )
            llm_text = (llm_result or {}).get("response", "") if llm_result else ""
            if llm_text:
                summary = llm_text
            evidence_citations = list((llm_result or {}).get("_rag_citations", []) or [])
        except Exception:
            pass  # LLM失败→保留规则生成的摘要

    record("shift_summary")
    summary_record = {
        "round_number": round_count,
        "summary": summary,
        "citations": evidence_citations,
        "timestamp": latest.get("timestamp", ""),
    }
    return {
        "shift_summary": summary,
        "shift_summary_citations": evidence_citations,
        "shift_summaries": [*(state.get("shift_summaries") or []), summary_record],
        "shift_summary_last_round": round_count,
        "clinical_evidence": merge_rag_citations(
            state.get("clinical_evidence"), evidence_citations
        ),
        "document_chain": chain + ["shift_summary"],
    }
