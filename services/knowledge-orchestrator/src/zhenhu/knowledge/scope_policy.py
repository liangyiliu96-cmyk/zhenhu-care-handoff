"""Deterministic metadata policy for governed knowledge recall."""

from __future__ import annotations

from typing import Any
import re


LAYER_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("L5", ("药", "用药", "剂量", "说明书", "禁忌", "不良反应", "相互作用", "抗生素", "利尿剂")),
    ("L6", ("检验", "化验", "指标", "血钾", "肌酐", "血常规", "参考值", "危急值")),
    ("L7", ("急症", "急救", "胸痛", "休克", "呼吸困难", "意识障碍", "抢救")),
    ("L8", ("护理", "导管", "压疮", "跌倒", "交班", "输液", "观察")),
    ("L9", ("患者教育", "宣教", "出院教育", "居家", "自我照护", "复诊", "随访")),
    ("L10", ("手术", "术后", "切口", "引流", "围手术")),
    ("L12", ("感染", "隔离", "消毒", "培养", "耐药", "mdro")),
    ("L13", ("营养", "饮食", "蛋白", "限盐", "限水", "体重")),
    ("L15", ("中医", "中药", "体质", "调养", "节气", "辨证")),
    ("L3", ("病种", "路径", "出院标准", "交接", "sop", "SOP")),
)

DISEASE_KEYWORDS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("heart_failure", "心内科", ("心衰", "心力衰竭", "容量管理", "利尿剂")),
    ("hypertension", "心内科", ("高血压", "血压")),
    ("cad", "心内科", ("冠心病", "心绞痛", "心肌梗死", "心梗")),
    ("atrial_fibrillation", "心内科", ("房颤", "心房颤动")),
    ("diabetes", "内分泌科", ("糖尿病", "血糖", "胰岛素")),
    ("pneumonia", "呼吸科", ("肺炎", "咳嗽", "咳痰", "抗感染")),
    ("copd", "呼吸科", ("慢阻肺", "copd", "COPD")),
    ("asthma", "呼吸科", ("哮喘", "喘息", "吸入器")),
    ("stroke", "神经内科", ("卒中", "中风", "脑梗", "脑出血")),
    ("ckd", "肾内科", ("慢性肾病", "CKD", "ckd", "肾功能")),
    ("aki", "肾内科", ("急性肾损伤", "AKI", "aki")),
    ("sepsis", "重症医学科", ("脓毒症", "感染性休克")),
    ("post_surgery", "外科", ("术后", "切口", "引流")),
)


def infer_knowledge_scope(
    *,
    title: str,
    owner: str,
    content: str = "",
    layer: str | None = None,
    disease_id: str | None = None,
    department: str | None = None,
) -> dict[str, str]:
    """Infer missing recall scope fields without overwriting explicit metadata."""
    text = " ".join(_text(value) for value in (title, owner, content))
    inferred_disease, disease_department = _infer_disease(text)
    resolved_department = _text(department) or _department_from_owner(owner) or disease_department
    return {
        "layer": _normalize_layer(layer) or _infer_layer(text),
        "disease_id": _text(disease_id) or inferred_disease,
        "department": resolved_department,
    }


SOURCE_TYPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("systematic_review", ("系统综述", "meta分析", "meta-analysis", "荟萃分析")),
    ("guideline", ("指南", "共识", "guideline", "consensus")),
    ("drug_label", ("说明书", "药品标签", "药品注册")),
    ("institutional_sop", ("sop", "流程", "路径", "操作规范")),
    ("primary_study", ("随机对照", "临床试验", "队列研究", "病例对照", "观察性研究")),
)

SOURCE_CREDIBILITY: dict[str, float] = {
    "systematic_review": 0.95,
    "guideline": 0.92,
    "drug_label": 0.90,
    "primary_study": 0.85,
    "institutional_sop": 0.80,
    "unknown": 0.50,
}


def infer_evidence_metadata(
    *,
    title: str,
    owner: str,
    content: str = "",
    source_type: str | None = None,
    evidence_level: str | None = None,
    guideline_year: int | None = None,
) -> dict[str, Any]:
    """Infer conservative EBM metadata and retain whether it was declared."""
    text = " ".join(_text(value) for value in (title, owner, content))
    normalized_type = _text(source_type).lower()
    if normalized_type not in SOURCE_CREDIBILITY:
        normalized_type = next((kind for kind, keywords in SOURCE_TYPE_KEYWORDS if any(keyword.lower() in text.lower() for keyword in keywords)), "unknown")
    normalized_level = _text(evidence_level).upper()
    if normalized_level not in {"A", "B", "C"}:
        normalized_level = _infer_evidence_level(text)
    resolved_year = guideline_year or _infer_guideline_year(text)
    declared = bool(_text(source_type) or _text(evidence_level) or guideline_year)
    return {
        "source_type": normalized_type,
        "evidence_level": normalized_level,
        "guideline_year": resolved_year,
        "source_credibility": SOURCE_CREDIBILITY.get(normalized_type, 0.5),
        "evidence_metadata_origin": "declared" if declared else "inferred",
    }


def _infer_evidence_level(text: str) -> str:
    value = text.lower()
    if any(term in value for term in ("系统综述", "meta分析", "meta-analysis", "随机对照", "临床试验")):
        return "A"
    if any(term in value for term in ("队列研究", "病例对照", "观察性研究")):
        return "B"
    if any(term in value for term in ("病例报告", "专家意见")):
        return "C"
    return "unknown"


def _infer_guideline_year(text: str) -> int | None:
    years = [int(value) for value in re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", text)]
    return max(years) if years else None


def apply_inferred_scope(document: Any, *, content: str = "") -> bool:
    """Mutate a document with inferred scope fields and return whether it changed."""
    scope = infer_knowledge_scope(
        title=getattr(document, "title", ""),
        owner=getattr(document, "owner", ""),
        content=content,
        layer=getattr(document, "layer", None),
        disease_id=getattr(document, "disease_id", None),
        department=getattr(document, "department", None),
    )
    changed = False
    for key, value in scope.items():
        if not _text(getattr(document, key, "")) and value:
            setattr(document, key, value)
            changed = True
    return changed


def _infer_layer(text: str) -> str:
    for layer, keywords in LAYER_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return layer
    return "L3"


def _infer_disease(text: str) -> tuple[str, str]:
    for disease_id, department, keywords in DISEASE_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return disease_id, department
    return "", ""


def _department_from_owner(owner: str) -> str:
    value = _text(owner)
    if "药学" in value:
        return "药学部"
    if "医务" in value:
        return "医务处"
    if value.endswith(("科", "部", "处")):
        return value
    return ""


def _normalize_layer(layer: str | None) -> str:
    value = _text(layer).upper()
    return value if value.startswith("L") else value


def _text(value: Any) -> str:
    return str(value or "").strip()
