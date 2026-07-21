"""外部临床数据源 — 公开免费 API 封装。

数据源:
  - ICD-10: clinicaltables.nlm.nih.gov (免费/无鉴权)
  - OpenFDA: api.fda.gov (免费/无鉴权)
  - RxNorm: rxnav.nlm.nih.gov (免费/无鉴权)

纯 HTTP + 超时 + 缓存，失败不阻断临床流程。
SKIP_EXTERNAL=true 跳过所有外部 API（测试用）。
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any

import httpx

logger = logging.getLogger("zhenhu.clinical_external")

SKIP_EXTERNAL = os.environ.get("SKIP_EXTERNAL", "").lower() in ("true", "1", "yes")

_CLIENT_TIMEOUT = httpx.Timeout(8.0, connect=4.0)
_DEFAULT_HEADERS = {"User-Agent": "Zhenhu-Inpatient/1.0"}

# 简单内存缓存（线程安全）
_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()


async def _get_cached(url: str, params: dict | None = None, ttl: int = 300) -> Any:
    """带缓存的 HTTP GET（线程安全）。"""
    if SKIP_EXTERNAL:
        return None
    cache_key = url + str(params or {})
    import time as _time
    now = _time.time()
    with _cache_lock:
        entry = _cache.get(cache_key)
        if entry and now - entry["ts"] < ttl:
            return entry["data"]
    try:
        async with httpx.AsyncClient(timeout=_CLIENT_TIMEOUT, headers=_DEFAULT_HEADERS) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            with _cache_lock:
                _cache[cache_key] = {"data": data, "ts": now}
                if len(_cache) > 500:
                    _cache.clear()
            return data
    except Exception as e:
        logger.warning("clinical_external: HTTP 请求失败 url=%s err=%s", url, e)
        return None


# ═══════════════════════════════════════════════════════════
# ICD-10 疾病编码查询
# ═══════════════════════════════════════════════════════════

ICD10_API = "https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"


async def icd10_search(term: str, max_results: int = 5) -> list[dict]:
    """ICD-10-CM 疾病编码查询。

    Example:
        >>> await icd10_search("hypertension")
        [{"code": "I15.0", "name": "Renovascular hypertension"}, ...]
    """
    data = await _get_cached(ICD10_API, {"sf": "code,name", "terms": term, "maxList": max_results})
    if not data or len(data) < 4:
        return []
    results = []
    for row in data[3]:
        if len(row) >= 2:
            results.append({"code": row[0], "name": row[1]})
    return results[:max_results]


async def icd10_lookup(code: str) -> dict | None:
    """ICD-10 编码→名称反查。"""
    data = await _get_cached(ICD10_API, {"sf": "code,name", "terms": code, "maxList": 1})
    if data and len(data) >= 4 and data[3]:
        row = data[3][0]
        return {"code": row[0], "name": row[1]} if len(row) >= 2 else None
    return None


# ═══════════════════════════════════════════════════════════
# OpenFDA 药物数据库
# ═══════════════════════════════════════════════════════════

OPENFDA_API = "https://api.fda.gov/drug/label.json"


async def drug_label(drug_name: str) -> dict | None:
    """OpenFDA 药物标签查询 — 返回警告/禁忌/适应症。

    Example:
        >>> await drug_label("amlodipine")
        {"warnings": "...", "indications": "...", "contraindications": "..."}
    """
    data = await _get_cached(OPENFDA_API, {"search": f'openfda.generic_name:"{drug_name}"', "limit": 1})
    if not data or not data.get("results"):
        return None
    label = data["results"][0]
    return {
        "warnings": (label.get("warnings") or [""])[0][:500] if label.get("warnings") else "",
        "indications": (label.get("indications_and_usage") or [""])[0][:300] if label.get("indications_and_usage") else "",
        "contraindications": (label.get("contraindications") or [""])[0][:300] if label.get("contraindications") else "",
        "adverse_reactions": (label.get("adverse_reactions") or [""])[0][:500] if label.get("adverse_reactions") else "",
        "drug_interactions": (label.get("drug_interactions") or [""])[0][:500] if label.get("drug_interactions") else "",
        "brand_name": (label.get("openfda", {}).get("brand_name") or [""])[0],
        "generic_name": (label.get("openfda", {}).get("generic_name") or [""])[0],
    }


async def drug_interactions(drug_a: str, drug_b: str) -> dict | None:
    """查询两种药物之间是否有已知相互作用。

    策略: 分别查询两个药物标签 → LLM 交叉分析。
    """
    label_a = await drug_label(drug_a)
    label_b = await drug_label(drug_b)
    if not label_a or not label_b:
        return None
    return {
        "drug_a": drug_a,
        "drug_b": drug_b,
        "label_a_warnings": label_a.get("warnings", ""),
        "label_b_warnings": label_b.get("warnings", ""),
        "label_a_interactions": label_a.get("drug_interactions", ""),
        "label_b_interactions": label_b.get("drug_interactions", ""),
    }


# ═══════════════════════════════════════════════════════════
# RxNorm 药物标准化
# ═══════════════════════════════════════════════════════════

RXNORM_API = "https://rxnav.nlm.nih.gov/REST"


async def rxnorm_id(drug_name: str) -> str | None:
    """药物名 → RxNorm ID (RxCUI)。

    Example:
        >>> await rxnorm_id("amlodipine")
        "17767"
    """
    data = await _get_cached(f"{RXNORM_API}/rxcui.json", {"name": drug_name, "search": "1"})
    if not data:
        return None
    ids = data.get("idGroup", {}).get("rxnormId", [])
    return ids[0] if ids else None


async def rxnorm_name(rxcui: str) -> str | None:
    """RxNorm ID → 标准药物名。"""
    data = await _get_cached(f"{RXNORM_API}/rxcui/{rxcui}/allrelated.json")
    if not data:
        return None
    groups = data.get("allRelatedGroup", {}).get("conceptGroup", [])
    for g in groups:
        props = g.get("conceptProperties", [])
        if props:
            return props[0].get("name")
    return None


# ═══════════════════════════════════════════════════════════
# 批量药物核对 (集成入口)
# ═══════════════════════════════════════════════════════════

async def enrich_medications(med_names: list[str]) -> list[dict]:
    """批量富化药物信息: 标准化名 + OpenFDA 警告 + RxNorm ID。

    供 node_medication_reconciliation 调用。
    """
    results = []
    for name in med_names:
        entry = {"original": name}
        try:
            rxcui = await rxnorm_id(name)
            if rxcui:
                entry["rxnorm_id"] = rxcui
                std_name = await rxnorm_name(rxcui)
                if std_name:
                    entry["standard_name"] = std_name
        except Exception:
            pass
        try:
            label = await drug_label(name)
            if label:
                entry["label"] = {
                    "warnings": label["warnings"][:200],
                    "contraindications": label["contraindications"][:200],
                    "interactions": label["drug_interactions"][:200],
                }
        except Exception:
            pass
        results.append(entry)
    return results


# ═══════════════════════════════════════════════════════════
# v0.3: 统一 Collect 入口 — DeepAgent 管线的 API 数据层
# ═══════════════════════════════════════════════════════════

async def collect_api_data(state: dict) -> dict:
    """Collect 阶段: 根据患者状态自动调取外部 API 数据。

    按优先级:
      1. 药物 FDA 标签 (如果有 medication_list)
      2. ICD-10 编码 (如果有 ddx)
      3. RxNorm 标准化 (如果有药物名)

    返回 {fda_labels, icd10_codes, rxnorm} 三字段
    """
    from collections import defaultdict

    result: dict[str, Any] = {}

    # 1. OpenFDA: 药物安全数据
    meds = state.get("medication_list") or []
    if not meds:
        findings = state.get("medication_findings", {}) or {}
        conflicts = findings.get("conflicts", []) or []
        if conflicts:
            meds = list(set(
                p for c in conflicts for p in c.get("drug_pair", "").split(" + ")
            ))[:8]

    if meds and os.environ.get("SKIP_EXTERNAL") != "true":
        try:
            labels = await get_drug_labels(meds[:5])
            if labels:
                result["fda_labels"] = [
                    {"drug": l.get("drug_name", ""), "warnings": l.get("warnings", "")[:200],
                     "contraindications": l.get("contraindications", "")[:200]}
                    for l in labels if l.get("drug_name")
                ]
        except Exception:
            pass

    # 2. ICD-10: 诊断标准化
    ddx = state.get("ddx_list") or state.get("diagnosis") or []
    if isinstance(ddx, str):
        ddx = [{"name": ddx}] if ddx else []
    if not ddx and isinstance(state.get("disease_template"), dict):
        ddx = [{"name": state["disease_template"].get("name", "")}]
    diagnoses = [d.get("name", "") if isinstance(d, dict) else str(d) for d in ddx[:3] if d]

    if diagnoses and os.environ.get("SKIP_EXTERNAL") != "true":
        try:
            icd_results = await search_icd10(diagnoses[0])
            if icd_results:
                result["icd10_codes"] = icd_results[:3]
        except Exception:
            pass

    return result


async def enrich_prompt_from_api(state: dict) -> str:
    """Collect 阶段: 生成 API 数据注入文本，用于拼接到 LLM prompt。"""
    data = await collect_api_data(state)
    if not data:
        return ""

    lines = ["【外部临床数据】"]
    if data.get("fda_labels"):
        lines.append("FDA药物安全:")
        for lbl in data["fda_labels"][:3]:
            lines.append(f"  {lbl['drug']}: {lbl['warnings'][:100]}")
    if data.get("icd10_codes"):
        lines.append("ICD-10编码:")
        for icd in data["icd10_codes"][:3]:
            lines.append(f"  {icd.get('code','?')} {icd.get('description','')[:80]}")
    return "\n".join(lines) if len(lines) > 1 else ""
