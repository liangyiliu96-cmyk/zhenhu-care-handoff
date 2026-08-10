"""临床智能助手引擎：能力模式路由、RAG、会话与流式输出。"""

from __future__ import annotations

import hashlib
import json
import logging
import time as _time
import re
from typing import Any, AsyncGenerator

logger = logging.getLogger("zhenhu.assistant")

# ── RAG 检索增强管线配置 ──
RAG_MIN_SCORE = 0.20       # 最低相似度阈值 (低于此值视为噪声, 降级为开放对话)
RAG_TOP_K = 5               # 向量检索召回数量
RAG_RERANK_TOP = 3          # 重排后保留数量
RAG_QUERY_EXPAND = True     # 是否启用问题改写/扩写

# ── 角色配置 ──
ROLE_CONFIG = {
    "doctor": {
        "name": "查房助手",
        "layers": ["L1","L2","L3","L4","L5","L6","L7","L9","L10","L11","L12","L13"],
        "system": "你是臻护查房助手，为医生提供循证决策支持。日常可寒暄闲聊。能力:诊断鉴别(DDx)/治疗方案优化/检查检验解读/用药安全评估/术后管理/出院标准判断/急症处置流程/营养支持/感染控制。可查患者数据(体征/用药/DDx/告警)给出个体化建议。回答包含核心建议+证据来源(LAYER标签)+注意事项。用中文，专业简洁。",
        "db_enabled": True,  # 允许查患者数据
    },
    "nurse": {
        "name": "护理助手",
        "layers": ["L1","L2","L3","L4","L5","L6","L7","L8","L9","L11","L12","L13","L14"],
        "system": "你是臻护护理助手，为护士提供全方位护理支持。日常可寒暄闲聊。能力:护理操作指导(压疮/跌倒/导管/PCA)/病情观察要点/用药安全管理/急诊识别/交接班要点/营养支持方案/感染控制措施/妇产专科护理/患者教育与自护。可查患者护理记录给出个体化建议。回答包含操作步骤+观察要点+注意事项。用中文，清晰实用。",
        "db_enabled": True,  # 允许查患者护理数据
    },
    "pharmacist": {
        "name": "用药助手",
        "layers": ["L1","L2","L5","L6","L7","L11","L12","L13"],
        "system": "你是臻护用药助手，提供药物全周期安全管理。日常可寒暄闲聊。能力:药物相互作用分析/剂量调整(肝肾功/体重/年龄)/特殊人群用药(孕妇/儿童/老年)/血药浓度监测(TDM)/不良反应识别/抗生素合理选择/营养药物支持/中西药联用评估。严重相互作用标记⚠️高危。可查FDA药品标签。用中文，精确专业。",
        "db_enabled": True,
    },
    "patient": {
        "name": "臻护健康小助手",
        "layers": ["L9","L13","L15"],
        "system": "你是臻护健康小助手，一个友善、温暖、有同理心的AI伙伴。能力:1)日常闲聊(天气/心情/兴趣爱好);2)健康问答(用药/饮食/康复/检查指标/中医调养/节气养生);3)平台介绍(臻护是什么/有什么功能)。核心原则:用简单中文，像朋友一样对话。健康问题需有依据，不确定时建议咨询医生。不评价医生方案，不推荐未经证实的偏方。",
        "db_enabled": False,
    },
    "integrative": {
        "name": "中西医协同助手",
        "layers": ["L1","L2","L3","L4","L5","L6","L7","L9","L13","L15"],
        "system": "你是臻护中西医协同助手，为出院评估提供中西医双视角。日常可寒暄闲聊。能力:六经辨证分析/中医体质评估(六项标准)/中药-西药交互检查/中医调养建议(饮食/节气/方药参考)/西医出院标准验证/患者教育与营养支持。标注每条建议来源(西医循证L1-L14/中医L15)。用中文，专业客观。",
        "db_enabled": True,
    },
}
DEFAULT_ROLE = "patient"

# 登录身份是授权边界，助手模式是业务能力。前端可提出模式请求，最终由路由层校验。
ASSISTANT_MODE_ACCESS = {
    "doctor": {"doctor", "pharmacist", "integrative", "patient"},
    "nurse": {"nurse", "patient"},
}

# Deterministic intent routing is deliberately used before an LLM call.  It
# is fast, explainable and cannot alter the clinical permission boundary.
INTENT_RULES = (
    ("emergency", "急症处置", ("胸痛", "呼吸困难", "休克", "抽搐", "意识", "出血", "危急", "高热"), ("L7", "L1")),
    ("medication", "用药安全", ("药", "剂量", "联用", "不良反应", "抗生素", "华法林", "肾功能"), ("L5", "L11", "L6")),
    ("laboratory", "检验解读", ("检验", "化验", "血常规", "肌酐", "钾", "inr", "指标"), ("L6", "L1")),
    ("discharge", "出院与随访", ("出院", "回家", "复诊", "随访", "宣教", "自我照护"), ("L3", "L9", "L13")),
    ("nursing", "护理执行", ("护理", "交班", "压疮", "导管", "输液", "跌倒", "班次"), ("L4", "L8", "L1")),
    ("infection", "感染控制", ("感染", "隔离", "消毒", "培养", "发热", "mdro"), ("L12", "L7")),
    ("nutrition", "营养支持", ("营养", "饮食", "体重", "蛋白", "吃什么"), ("L13", "L9")),
    ("surgery", "围手术期", ("手术", "术后", "伤口", "引流", "切口"), ("L10", "L8")),
    ("integrative", "中西医协同", ("中医", "体质", "调养", "节气", "中药"), ("L15", "L16", "L5")),
)

SMALLTALK_MESSAGES = {
    "hi",
    "hello",
    "你好",
    "您好",
    "嗨",
    "哈喽",
    "早上好",
    "上午好",
    "中午好",
    "下午好",
    "晚上好",
    "晚安",
    "在吗",
    "谢谢",
    "谢谢你",
    "多谢",
    "再见",
    "拜拜",
    "你是谁",
    "你叫什么",
    "你叫什么名字",
    "你能做什么",
}
SMALLTALK_SUFFIX_PARTICLES = "呀啊哦呢啦"

# ── 预设快捷问题 ──
QUICK_QUESTIONS = {
    "doctor": [
        "该患者目前最关键的行动建议？",
        "鉴别诊断需要考虑哪些疾病？",
        "出院标准是否全部达标？",
        "药物方案如何优化调整？",
        "需要加做哪些进一步检查？",
        "术后管理有哪些要点？",
    ],
    "nurse": [
        "本班次需重点关注哪些患者？",
        "该患者压疮风险评估及预防措施",
        "交接班时必须交代什么？",
        "导管/引流管护理注意事项",
        "如何判断患者病情是否恶化？",
        "术后患者的护理要点是什么？",
    ],
    "pharmacist": [
        "肾功能不全时这个药怎么调剂量？",
        "两种药联用有什么相互作用风险？",
        "老年患者用药需要减量吗？",
        "这个药的常见不良反应有哪些？",
        "中药和西药能一起吃吗？",
        "抗生素疗程多久合适？",
    ],
    "integrative": [
        "该患者中医体质倾向是什么？",
        "出院后饮食调养有何建议？",
        "所用西药与中药有无冲突？",
        "当前节气养生的要点？",
        "该病在六经辨证中属哪一经？",
    ],
    "patient": [
        "感冒了吃什么药好得快？", "失眠怎么办？", "降压药可以停吗？",
        "便秘吃什么食物？", "运动后肌肉酸痛怎么办？",
        "春天吃什么养生？", "今天感觉不舒服怎么办？",
    ],
}

GENERAL_QUICK_QUESTIONS = {
    "doctor": [
        "如何系统评估住院患者的 NEWS2 风险？",
        "心力衰竭利尿治疗需要重点监测什么？",
        "出院前常见的用药核对要点有哪些？",
        "何时应发起多学科会诊？",
    ],
    "nurse": [
        "交接班时应优先核对哪些风险？",
        "体征异常升级上报的关键要点是什么？",
        "如何完成患者宣教的回授确认？",
        "高风险患者的床旁观察要点有哪些？",
    ],
    "pharmacist": [
        "常见肝肾功能不全患者如何评估剂量调整？",
        "药物相互作用核对时应优先关注哪些风险？",
        "老年患者多重用药核对有哪些关键步骤？",
        "抗菌药物疗程评估通常需要哪些信息？",
    ],
    "integrative": [
        "中西医协同评估应分别核对哪些信息？",
        "中药与西药联用时如何开展风险核对？",
        "出院调养建议如何兼顾循证与个体差异？",
        "中医体质评估结果应如何谨慎解释？",
    ],
    "patient": [
        "长期服药时有哪些通用安全注意事项？",
        "出院后出现哪些症状需要尽快就医？",
        "如何记录血压、血糖等居家健康数据？",
        "复诊前应该准备哪些资料？",
    ],
}


def quick_questions_for(role: str, context: str = "patient") -> list[str]:
    """Return role-scoped prompts without implying patient context for general use."""
    if context == "general":
        return GENERAL_QUICK_QUESTIONS.get(role, GENERAL_QUICK_QUESTIONS["patient"])
    return QUICK_QUESTIONS.get(role, QUICK_QUESTIONS.get("patient", []))
SESSION_TTL, MAX_HISTORY = 1800, 10

# ── 会话管理 ──
_sessions: dict[str, dict] = {}
_redis_client = False


def _get_redis():
    global _redis_client
    if _redis_client is False or _redis_client is None:
        try:
            from ..services.runtime_cache import get_runtime_cache

            client = get_runtime_cache().redis_client()
            if client is None:
                raise RuntimeError("Redis unavailable")
            recovered = _redis_client is None
            _redis_client = client
            logger.info("Assistant: Redis session backend %s", "reconnected" if recovered else "ready")
        except Exception:
            if _redis_client is False:
                logger.info("Assistant: 使用内存会话")
            _redis_client = None
    return _redis_client


def _save(sid, data):
    global _redis_client
    r = _get_redis()
    if r:
        try:
            r.set(f"asst:{sid}", json.dumps(data, ensure_ascii=False), ex=SESSION_TTL)
            owner_id = str(data.get("owner_id") or "")
            if owner_id:
                index_key = _owner_index_key(owner_id)
                r.zadd(index_key, {sid: _time.time()})
                r.expire(index_key, SESSION_TTL)
            return
        except Exception:
            _redis_client = None
            logger.warning("Assistant Redis save failed; using in-memory session")
    _sessions[sid] = {"data": data, "expires": _time.time() + SESSION_TTL}


def _load(sid):
    global _redis_client
    r = _get_redis()
    if r:
        try:
            raw = r.get(f"asst:{sid}")
            return json.loads(raw) if raw else None
        except Exception:
            _redis_client = None
            logger.warning("Assistant Redis load failed; checking in-memory session")
    e = _sessions.get(sid)
    return e["data"] if e and _time.time() < e["expires"] else None


def create_session(role=DEFAULT_ROLE, patient_id="", *, owner_id=""):
    import uuid
    sid = uuid.uuid4().hex[:12]
    assistant_mode = role if role in ROLE_CONFIG else DEFAULT_ROLE
    _save(sid, {
        "role": assistant_mode,
        "assistant_mode": assistant_mode,
        "patient_id": patient_id,
        "owner_id": str(owner_id),
        "history": [],
        "created_at": _time.time(),
    })
    return sid


def add_message(sid, role, content):
    sess = _load(sid)
    if not sess: return
    sess["history"].append({"role": role, "content": content, "time": _time.time()})
    if len(sess["history"]) > MAX_HISTORY * 2: sess["history"] = sess["history"][-(MAX_HISTORY*2):]
    _save(sid, sess)


def get_history(sid): 
    s = _load(sid); return s.get("history", []) if s else []


def get_session(sid):
    s = _load(sid)
    return {
        "session_id": sid,
        "role": s.get("assistant_mode") or s.get("role"),
        "assistant_mode": s.get("assistant_mode") or s.get("role"),
        "patient_id": s.get("patient_id"),
        "history": s.get("history", []),
        "created_at": s.get("created_at"),
    } if s else None


def assistant_message_reference(sid: str, source_text: str) -> str | None:
    """Return a stable reference only for an assistant reply stored in this session."""
    session = _load(sid)
    if not session:
        return None
    normalized = source_text.strip()
    for index in range(len(session.get("history", [])) - 1, -1, -1):
        message = session["history"][index]
        if message.get("role") == "assistant" and str(message.get("content") or "").strip() == normalized:
            digest = hashlib.sha256(f"{sid}:{index}:{normalized}".encode("utf-8")).hexdigest()[:24]
            return f"assistant-message-{digest}"
    return None


def can_access_session(sid: str, actor_id: str) -> bool:
    """Session identifiers are not authorization credentials."""
    session = _load(sid)
    return bool(session and actor_id and session.get("owner_id") == str(actor_id))


def reset_session(sid):
    s = _load(sid)
    if s: s["history"] = []; _save(sid, s)


def session_stats():
    r = _get_redis()
    if r:
        try: return {"backend": "redis", "active_sessions": int(r.dbsize())}
        except: pass
    return {"backend": "memory", "active_sessions": len(_sessions)}


def sessions_for_owner(actor_id: str) -> list[dict]:
    """Return metadata only for sessions owned by the authenticated actor."""
    if not actor_id:
        return []
    sessions: list[dict] = []
    r = _get_redis()
    if r:
        try:
            index_key = _owner_index_key(str(actor_id))
            for sid in r.zrevrange(index_key, 0, 99):
                session = _load(sid)
                if session and session.get("owner_id") == str(actor_id):
                    sessions.append(_session_summary(sid, session))
                elif not session:
                    r.zrem(index_key, sid)
        except Exception:
            pass
    else:
        now = _time.time()
        for sid, entry in list(_sessions.items()):
            if entry.get("expires", 0) <= now:
                _sessions.pop(sid, None)
                continue
            session = entry.get("data") or {}
            if session.get("owner_id") == str(actor_id):
                sessions.append(_session_summary(sid, session))
    return sorted(sessions, key=lambda item: item["updated_at"], reverse=True)


def _session_summary(sid: str, session: dict) -> dict:
    history = session.get("history") or []
    return {"session_id": sid, "assistant_mode": session.get("assistant_mode") or session.get("role"), "patient_id": session.get("patient_id") or "", "created_at": session.get("created_at"), "updated_at": history[-1].get("time") if history else session.get("created_at"), "message_count": len(history)}


def _owner_index_key(actor_id: str) -> str:
    digest = hashlib.sha256(actor_id.encode("utf-8")).hexdigest()[:24]
    return f"asst:owner:{digest}"


# ── 核心引擎 ──

def _build_prompt(sources, session_id, config, message):
    """构建自适应 prompt — 有知识则专业，无知识则友好闲聊。"""
    history = get_history(session_id)
    htext = "\n".join(f"{'用户' if h['role']=='user' else '助手'}: {h['content'][:200]}" for h in history[-MAX_HISTORY:]) if history else ""

    if sources:
        rtext = "【循证依据】\n" + "\n".join(f"[{s['layer']}] {s['topic']}: {s['text']}" for s in sources)
        return f"{config['system']}\n\n{rtext}\n\n【对话历史】\n{htext}\n\n【当前问题】\n{message}\n\n请基于循证依据给出专业回答，标注信息来源。如依据不足请说明。最终仅返回 JSON 对象，必须包含 answer 字段，answer 的值为完整中文回答。"

    # 无知识命中 → 开放对话模式
    return f"{config['system']}\n\n【对话历史】\n{htext}\n\n【当前问题】\n{message}\n\n请友善自然地回答。如果是健康问题就坦诚说需要更多信息并建议咨询医生，如果是日常闲聊就轻松回应。最终仅返回 JSON 对象，必须包含 answer 字段，answer 的值为完整中文回答。"


def classify_intent(message: str, allowed_layers: list[str]) -> dict[str, Any]:
    """Classify intent locally and return only layers the active assistant may use."""
    normalized = message.lower()
    compact_message = re.sub(r"[\W_]+", "", normalized)
    smalltalk_core = compact_message.rstrip(SMALLTALK_SUFFIX_PARTICLES)
    if compact_message in SMALLTALK_MESSAGES or smalltalk_core in SMALLTALK_MESSAGES:
        return {
            "name": "smalltalk",
            "label": "日常寒暄",
            "confidence": 0.99,
            "layers": [],
            "matched_keywords": [],
        }
    matches: list[tuple[int, str, str, tuple[str, ...]]] = []
    for name, label, keywords, layers in INTENT_RULES:
        matched = sum(1 for keyword in keywords if keyword.lower() in normalized)
        if matched:
            matches.append((matched, name, label, layers))
    if not matches:
        return {"name": "general", "label": "通用咨询", "confidence": 0.35, "layers": list(allowed_layers), "matched_keywords": []}
    matches.sort(key=lambda item: item[0], reverse=True)
    score, name, label, proposed_layers = matches[0]
    routed_layers = [layer for layer in proposed_layers if layer in allowed_layers]
    return {
        "name": name,
        "label": label,
        "confidence": min(0.95, 0.55 + score * 0.15),
        "layers": routed_layers or list(allowed_layers),
        "matched_keywords": [keyword for keyword in next(rule[2] for rule in INTENT_RULES if rule[0] == name) if keyword.lower() in normalized],
    }


def _general_answer_cache_key(role: str, message: str, intent: dict[str, Any]) -> str:
    from .rag_engine import rag_runtime_status

    payload = {
        "revision": rag_runtime_status()["index_revision"],
        "role": role,
        "intent": intent.get("name"),
        "message": message.strip(),
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return f"assistant:general:{digest}"


def _patient_answer_cache_key(role: str, message: str, intent: dict[str, Any], patient_id: str, state_version: str) -> str:
    """患者相关问题的缓存 key — 带 patient_id + state_version 防止状态过时。"""
    from .rag_engine import rag_runtime_status

    payload = {
        "revision": rag_runtime_status()["index_revision"],
        "role": role,
        "intent": intent.get("name"),
        "message": message.strip()[:200],  # 截断防key过长
        "patient_id": patient_id,
        "state_version": state_version,
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return f"assistant:patient:{digest}"


def _is_smalltalk(intent: dict[str, Any]) -> bool:
    return intent.get("name") == "smalltalk"


def _is_general_cache_safe(message: str) -> bool:
    """Never share answers derived from likely patient-identifying free text."""
    normalized = message.lower()
    blocked_terms = ("患者", "病人", "床号", "住院号", "病历号", "身份证", "电话", "手机号", "姓名")
    return len(message) <= 400 and not any(term in normalized for term in blocked_terms) and re.search(r"\d{6,}", normalized) is None


async def _retrieve_sources(message: str, config: dict) -> tuple[list[dict], list[dict], dict[str, Any]]:
    intent = classify_intent(message, config["layers"])
    if intent["name"] == "smalltalk" or not intent["layers"]:
        return [], [], intent
    try:
        from .rag_engine import search as rag_search

        # ── 第1步: 问题改写/扩写 ──
        queries = _expand_query(message)

        # ── 第2步: 多查询向量检索 (去重合并) ──
        all_hits: list[dict] = []
        seen_texts: set[str] = set()
        for q in queries[:3]:  # 最多3个改写查询
            hits = await rag_search(q, layer=intent["layers"], top_k=RAG_TOP_K)
            for hit in hits:
                text_key = str(hit.get("topic","")) + str(hit.get("text",""))[:80]
                if text_key not in seen_texts:
                    seen_texts.add(text_key)
                    all_hits.append(hit)

        if not all_hits:
            return [], [], intent

        # ── 第3步: 按层过滤 ──
        allowed = set(intent["layers"])
        layer_hits = [h for h in all_hits if h.get("layer") in allowed]
        if not layer_hits:
            # fallback: 层过滤无结果则取全部命中
            layer_hits = all_hits

        # ── 第4步: 分数阈值过滤 (去除噪声) ──
        scored_hits = [h for h in layer_hits if h.get("score", 0) >= RAG_MIN_SCORE]

        # ── 第5步: 重排序 ──
        if len(scored_hits) > RAG_RERANK_TOP:
            scored_hits = _rerank_hits(message, scored_hits)[:RAG_RERANK_TOP]

        # ── 第6步: 构建引用 ──
        sources = [
            {
                "layer": hit.get("layer"),
                "topic": hit.get("topic"),
                "text": str(hit.get("text") or "")[:150],
            }
            for hit in scored_hits[:RAG_RERANK_TOP]
        ]
        from ..services.clinical_evidence import build_rag_citations

        return sources, build_rag_citations(scored_hits[:RAG_RERANK_TOP]), intent
    except Exception as exc:
        logger.info("Assistant RAG unavailable: %s", exc)
        return [], [], intent


# ── 检索增强管线 辅助函数 ──

def _expand_query(message: str) -> list[str]:
    """问题改写: 从原问题生成2-3个变体查询, 提升召回覆盖率。

    策略: 关键词提取 + 同义词替换 + 原始问题保留。
    不调用 LLM (零额外延迟), 使用临床领域同义词映射。
    """
    if not RAG_QUERY_EXPAND:
        return [message]

    queries = [message]  # 原始问题始终保留

    # 临床同义词映射 (30组, 覆盖心内/呼吸/神内/内分泌/产科/外科/护理高频口语→术语)
    SYNONYMS = {
        # 心内科
        "心衰": ["心力衰竭", "心脏功能不全", "心功能不全"],
        "房颤": ["心房颤动", "心律失常", "心跳不齐"],
        "心梗": ["心肌梗死", "心肌梗塞", "冠心病发作"],
        "胸痛": ["胸部疼痛", "胸闷", "心前区不适"],
        # 呼吸科
        "喘": ["呼吸困难", "气喘", "喘息", "呼吸急促"],
        "吸氧": ["氧疗", "给氧", "氧气治疗"],
        "咳嗽": ["咳", "干咳", "咳痰"],
        # 内分泌
        "血糖低": ["低血糖", "血糖过低", "低血糖症"],
        "血糖高": ["高血糖", "血糖过高", "高血糖症"],
        "糖尿病": ["消渴", "血糖病"],
        # 护理通用
        "褥疮": ["压疮", "压力性损伤", "褥疮性溃疡"],
        "管子": ["导管", "引流管", "管路", "插管"],
        "三查七对": ["查对制度", "核对制度"],
        "输液": ["静脉输液", "补液", "打点滴", "打吊针"],
        "腿肿": ["下肢水肿", "腿部肿胀", "水肿", "浮肿"],
        "吃药": ["用药", "服药", "药物", "吃药片"],
        "手术后": ["术后", "围手术期", "开刀后"],
        "怎么办": ["处理", "护理", "处置", "应对"],
        "预防": ["防止", "防控", "避免"],
        "伤口": ["创口", "切口", "刀口"],
        "发烧": ["发热", "体温升高", "高热", "发烧了"],
        # 神内科
        "中风": ["脑卒中", "脑血管意外", "脑梗塞", "脑梗死", "脑出血"],
        "头晕": ["眩晕", "头昏", "眼花"],
        # 产科
        "生孩子": ["分娩", "生产", "顺产"],
        "剖腹产": ["剖宫产", "剖腹生产"],
        "产后": ["生完孩子后", "分娩后"],
        # 外科
        "开刀": ["手术", "开刀手术"],
        "拆线": ["拆除缝线", "拆缝合线"],
        # 肾内科
        "透析": ["血液透析", "腹膜透析", "血透", "腹透"],
        "小便少": ["少尿", "无尿", "尿少", "尿量减少"],
        # 检验/监测
        "血气": ["血气分析", "动脉血气", "血气检查"],
        "心电图": ["心电图检查", "ECG", "心脏电图"],
        # 症状
        "疼痛": ["痛", "疼", "剧痛", "隐痛", "NRS评分"],
        "抽筋": ["抽搐", "惊厥", "癫痫发作", "痉挛"],
        "出血": ["流血", "出血不止", "渗血", "大出血"],
        "过敏": ["过敏反应", "起疹子", "皮疹", "荨麻疹"],
        "恶心": ["反胃", "想吐", "呕吐", "干呕"],
        "便血": ["黑便", "柏油样便", "消化道出血", "大便带血"],
        # 感染
        "感染": ["发炎", "炎症", "化脓"],
        "消毒": ["杀菌", "灭菌", "清洁消毒"],
    }

    expanded = message
    for key, syns in SYNONYMS.items():
        if key in message:
            for syn in syns:
                expanded_variant = message.replace(key, syn)
                if expanded_variant != message and expanded_variant not in queries:
                    queries.append(expanded_variant)
                    if len(queries) >= 3:
                        break
        if len(queries) >= 3:
            break

    # 如果原问题较长, 提取关键短句作为额外查询
    if len(queries) < 2 and len(message) > 15:
        # 提取前10-15个字符作为短查询 (通常是主诉关键词)
        short = message[:15].rstrip("，。,.")
        if short != message and len(short) >= 4:
            queries.append(short)

    return queries[:3]


def _rerank_hits(query: str, hits: list[dict]) -> list[dict]:
    """轻量级重排序: 基于关键词覆盖 + 长度适中的启发式评分。

    不依赖 cross-encoder (零额外延迟), 适合嵌入到现有管线。
    未来可升级为 BAAI/bge-reranker-v2-m3 等专用重排模型。
    """
    if len(hits) <= RAG_RERANK_TOP:
        return hits

    query_lower = query.lower()
    query_chars = set(query_lower)

    def heuristic_score(hit: dict) -> float:
        text = str(hit.get("text", "")).lower()
        topic = str(hit.get("topic", "")).lower()

        # 基础分数 = 向量相似度 (权重 0.6)
        base = hit.get("score", 0) * 0.6

        # 关键词覆盖分数 (权重 0.25)
        text_chars = set(text)
        topic_chars = set(topic)
        char_overlap = len(query_chars & text_chars) / max(len(query_chars), 1)
        topic_match = 0.15 if any(c in topic for c in query_lower.split()) else 0
        keyword_score = char_overlap * 0.25 + topic_match

        # 长度适中性 (权重 0.15) — 100-300字最优, 太短太长发散
        length = len(hit.get("text", ""))
        if 100 <= length <= 300:
            length_score = 0.15
        elif 50 <= length <= 500:
            length_score = 0.10
        else:
            length_score = 0.05

        return base + keyword_score + length_score

    scored = [(hit, heuristic_score(hit)) for hit in hits]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [hit for hit, _ in scored]


def _answer_from_result(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    for key in ("answer", "response", "content", "result"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


async def _get_provider():
    from .llm_utils import get_provider_for_node

    return get_provider_for_node("assistant"), "configured"


async def extract_action_draft_suggestions(source_text: str) -> list[dict[str, Any]]:
    """Extract executable suggestions without performing a clinical mutation."""
    provider, _ = await _get_provider()
    prompt = f"""你是临床操作草稿结构化器。仅抽取下方医生助手回答中明确、可执行的建议，不得补充回答中没有的信息。
允许类型只有 medication_order、investigation_order、follow_up_task、mdt_request、education_plan。
medication_order.payload 必须包含 medication、dose、frequency，可选 route、indication。
investigation_order.payload 必须包含 test_name、reason，可选 priority(routine|urgent)、timing、instructions。
follow_up_task.payload 必须包含 title、due_at，可选 assignee。due_at 必须是明确的 ISO 8601 时间；若回答只有“数日后”等模糊时间，不要生成随访草稿。
信息不完整的建议不要生成。最多返回 5 条。仅返回 JSON：{{"drafts":[{{"draft_type":"...","payload":{{...}},"rationale":"原回答中的理由"}}]}}。

【助手回答】
{source_text[:12000]}"""
    from .llm_utils import safe_llm_invoke

    # Keep draft extraction within the frontend agent-operation timeout budget.
    result = await safe_llm_invoke(provider, prompt, timeout=20.0, retries=0, caller="assistant_action_drafts")
    payload = _structured_result(result)
    drafts = payload.get("drafts", []) if isinstance(payload, dict) else []
    return [item for item in drafts[:5] if isinstance(item, dict)] if isinstance(drafts, list) else []


def _structured_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    if isinstance(result.get("drafts"), list):
        return result
    for key in ("response", "answer", "content", "result"):
        value = result.get(key)
        if not isinstance(value, str):
            continue
        raw = value.strip()
        if raw.startswith("```"):
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _patient_context(patient_id: str, *, include_readiness: bool) -> str:
    """Build assistant context from the canonical patient state API, not a backend-specific connection."""
    if not patient_id:
        return ""
    try:
        from ..routes.state_store import get_state

        state = get_state(patient_id)
        if not state:
            return ""
        template = state.get("disease_template") or {}
        vitals = (state.get("vital_signs") or [])[-2:]
        medications = [
            str(item.get("drug_name") or item.get("medication") or item.get("drug") or "")
            for item in (state.get("medication_adjustments") or [])[:5]
        ]
        ddx = [str(item.get("diagnosis") or "") for item in (state.get("ddx_list") or [])[:3]]
        alerts = [str(item) for item in (state.get("clinical_alerts") or [])[:2]]
        criteria = state.get("discharge_criteria_check") or {}
        parts = [f"病种:{template.get('name', '未知')} | 风险:{state.get('risk_level', '?')} | NEWS2:{state.get('news2_score', '?')}"]
        if include_readiness:
            readiness = (state.get("discharge_readiness") or {}).get("score", "?")
            parts[0] = f"{parts[0]} | 出院准备度:{readiness}"
        if ddx:
            parts.append(f"诊断:{','.join(item for item in ddx if item)}")
        if vitals:
            parts.append("体征:" + " | ".join(
                f"{item.get('spo2', '?')}%/{item.get('systolic_mmhg', '?')}/{item.get('diastolic_mmhg', '?')}/HR{item.get('heart_rate', '?')}/T{item.get('temperature', '?')}"
                for item in vitals
            ))
        if any(medications):
            parts.append(f"用药:{','.join(item for item in medications if item)}")
        if alerts:
            parts.append(f"告警:{' | '.join(alerts)}")
        if criteria.get("unmet"):
            parts.append(f"出院未达标:{','.join(criteria['unmet'][:3])}")
        return "【当前患者数据】\n" + "\n".join(parts)
    except Exception as exc:
        logger.debug("Assistant patient context unavailable: %s", exc)
        return ""


async def chat(message: str, role=DEFAULT_ROLE, session_id=None, patient_id="", actor_id="") -> dict:
    """助手对话 — 完整回答。"""
    if role not in ROLE_CONFIG: role = DEFAULT_ROLE
    config = ROLE_CONFIG[role]
    if not session_id: session_id = create_session(role, patient_id, owner_id=actor_id)
    add_message(session_id, "user", message)

    # 患者上下文注入 (医生/护士助手专属，传 patient_id 自动拉数据)
    patient_context = _patient_context(patient_id, include_readiness=True) if config.get("db_enabled") else ""

    sources, citations, intent = await _retrieve_sources(message, config)
    # 缓存：通用问题（无患者）用简单 key，有患者时加入 patient_id+版本号防止过时
    state_version_slug = ""
    if patient_id:
        try:
            from ..routes.state_store import get_state
            state_version_slug = str((get_state(patient_id) or {}).get("state_version", ""))
        except Exception:
            pass
    cache_key = _patient_answer_cache_key(role, message, intent, patient_id, state_version_slug) if not _is_smalltalk(intent) else ""
    if cache_key:
        from ..services.runtime_cache import get_runtime_cache

        cached = get_runtime_cache().get_json(cache_key)
        if isinstance(cached, dict) and isinstance(cached.get("answer"), str):
            answer = cached["answer"]
            sources = cached.get("sources") if isinstance(cached.get("sources"), list) else sources
            citations = cached.get("citations") if isinstance(cached.get("citations"), list) else citations
            add_message(session_id, "assistant", answer)
            return {
                "answer": answer, "sources": sources, "citations": citations,
                "confidence": cached.get("confidence", 0.65), "session_id": session_id,
                "role": role, "assistant_name": config["name"], "intent": intent,
                "health": {"rag": "ok" if sources else "degraded", "llm": "cached", "session": session_stats().get("backend", "memory"), "backend": "redis-cache", "cache_hit": True},
            }

    prompt = _build_prompt(sources, session_id, config, message)
    if patient_context:
        prompt = f"{patient_context}\n\n{prompt}"
    provider, backend = await _get_provider()

    # LLM
    answer = ""
    health = {"rag": "ok" if sources else "degraded", "llm": "ok", "session": session_stats().get("backend", "memory"), "backend": backend}
    try:
        import asyncio
        from .llm_utils import safe_llm_invoke
        result = await asyncio.wait_for(safe_llm_invoke(provider, prompt, timeout=90.0, caller=f"asst_{role}"), timeout=120.0)
        answer = _answer_from_result(result)
    except asyncio.TimeoutError:
        answer = "⚠️ AI 推理超时。请稍后重试或简化问题。"; health["llm"] = "timeout"
    except Exception as e:
        answer = "⚠️ 服务暂不可用。"; health["llm"] = "error"
    if not answer: answer = "⚠️ 知识库暂不可用。请稍后重试。"; health["llm"] = "empty"

    add_message(session_id, "assistant", answer)
    confidence = round(min(0.95, 0.5+len(sources)*0.15), 2)
    if cache_key and health["llm"] == "ok":
        from ..services.runtime_cache import get_runtime_cache

        get_runtime_cache().set_json(cache_key, {"answer": answer, "sources": sources, "citations": citations, "confidence": confidence}, 3600)
    return {"answer": answer, "sources": sources, "citations": citations, "confidence": confidence,
            "session_id": session_id, "role": role, "assistant_name": config["name"], "intent": intent, "health": health}


async def chat_stream(message: str, role=DEFAULT_ROLE, session_id=None, patient_id="", actor_id="") -> AsyncGenerator[str, None]:
    """流式输出 — SSE 格式, 逐 token 返回。"""
    import asyncio

    if role not in ROLE_CONFIG: role = DEFAULT_ROLE
    config = ROLE_CONFIG[role]
    if not session_id: session_id = create_session(role, patient_id, owner_id=actor_id)
    add_message(session_id, "user", message)

    # 患者上下文注入
    patient_context = _patient_context(patient_id, include_readiness=False) if config.get("db_enabled") else ""

    sources, citations, intent = await _retrieve_sources(message, config)
    state_version_slug = ""
    if patient_id:
        try:
            from ..routes.state_store import get_state
            state_version_slug = str((get_state(patient_id) or {}).get("state_version", ""))
        except Exception:
            pass
    cache_key = _patient_answer_cache_key(role, message, intent, patient_id, state_version_slug) if not _is_smalltalk(intent) else ""
    if cache_key:
        from ..services.runtime_cache import get_runtime_cache

        cached = get_runtime_cache().get_json(cache_key)
        if isinstance(cached, dict) and isinstance(cached.get("answer"), str):
            answer = cached["answer"]
            sources = cached.get("sources") if isinstance(cached.get("sources"), list) else sources
            citations = cached.get("citations") if isinstance(cached.get("citations"), list) else citations
            add_message(session_id, "assistant", answer)
            for index in range(0, len(answer), 5):
                yield f"data: {json.dumps({'token': answer[index:index + 5], 'done': False}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.005)
            yield f"data: {json.dumps({'token': '', 'done': True, 'session_id': session_id, 'sources': [s['topic'] for s in sources], 'citations': citations, 'backend': 'redis-cache', 'cache_hit': True, 'intent': intent}, ensure_ascii=False)}\n\n"
            return

    prompt = _build_prompt(sources, session_id, config, message)
    if patient_context:
        prompt = f"{patient_context}\n\n{prompt}"

    try:
        provider, _ = await _get_provider()
        from .llm_utils import safe_llm_invoke

        result = await asyncio.wait_for(
            safe_llm_invoke(provider, prompt, timeout=90.0, caller=f"asst_{role}"),
            timeout=120.0,
        )
        answer = _answer_from_result(result)
        if answer:
            add_message(session_id, "assistant", answer)
            if cache_key:
                from ..services.runtime_cache import get_runtime_cache

                get_runtime_cache().set_json(cache_key, {"answer": answer, "sources": sources, "citations": citations, "confidence": round(min(0.95, 0.5 + len(sources) * 0.15), 2)}, 3600)
            for index in range(0, len(answer), 5):
                token = answer[index:index + 5]
                yield f"data: {json.dumps({'token': token, 'done': False}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.01)
            backend = getattr(provider, "model", provider.__class__.__name__)
            yield f"data: {json.dumps({'token': '', 'done': True, 'session_id': session_id, 'sources': [s['topic'] for s in sources], 'citations': citations, 'backend': backend, 'cache_hit': False, 'intent': intent}, ensure_ascii=False)}\n\n"
            return
    except Exception as exc:
        logger.warning("Assistant stream failed for %s: %s", role, exc)

    # 兜底
    fallback = "⚠️ 服务暂不可用，请稍后重试。"
    add_message(session_id, "assistant", fallback)
    yield f"data: {json.dumps({'token': fallback, 'done': True, 'session_id': session_id, 'sources': [s['topic'] for s in sources], 'citations': citations, 'backend': 'fallback', 'cache_hit': False, 'intent': intent}, ensure_ascii=False)}\n\n"
