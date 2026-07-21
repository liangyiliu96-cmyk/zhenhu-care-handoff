"""工业级 RAG 知识引擎 — Milvus 向量数据库 + sentence-transformers。

四层知识架构:
  L1: clinical_scoring  — 6 项临床评分规则
  L2: disease_keypoints — 18 个疾病诊治要点
  L3: disease_templates — 18 个病种模板
  L4: dept_protocols    — 12 科室护理清单
"""

from __future__ import annotations

import json, logging, os, time as _time, glob, hashlib
from collections.abc import Iterable
from typing import Any
from collections import OrderedDict
from threading import Lock
import numpy as np

logger = logging.getLogger("zhenhu.rag_engine")

MILVUS_HOST = os.environ.get("MILVUS_HOST", "localhost")
MILVUS_PORT = os.environ.get("MILVUS_PORT", "19530")
DIM = 384  # MiniLM

# 查询向量 LRU 缓存 (相同问题秒回, 最大 512 条)
_enc_cache: OrderedDict[str, Any] = OrderedDict()
_ENC_CACHE_MAX = int(os.environ.get("RAG_ENC_CACHE_MAX", "512"))

# 向量模型: 可通过 RAG_MODEL 环境变量切换更优的中文模型
#   paraphrase-multilingual-MiniLM-L12-v2  (默认, 384维, 轻量)
#   moka-ai/m3e-base                       (768维, 中文优化, Recall +10-15%)
#   BAAI/bge-large-zh-v1.5                 (1024维, 中文最佳, Recall +15-20%)
RAG_MODEL = os.environ.get("RAG_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
RAG_IVF_NLIST = int(os.environ.get("RAG_IVF_NLIST", "128"))  # IVF_FLAT 聚类数, 0=不建索引
RAG_SEARCH_CACHE_TTL = max(30, int(os.environ.get("RAG_SEARCH_CACHE_TTL", "600")))
RAG_EMBEDDING_CACHE_TTL = max(300, int(os.environ.get("RAG_EMBEDDING_CACHE_TTL", "86400")))

LAYERS = {"L1":"clinical_scoring","L2":"disease_keypoints","L3":"disease_templates","L4":"dept_protocols",
          "L5":"drug_safety","L6":"lab_reference","L7":"emergency_protocols","L8":"nursing_protocols",
          "L9":"patient_education","L10":"surgical_protocols","L11":"medication_dosing",
          "L12":"infection_control","L13":"nutrition_support","L14":"obgyn_basics",
          "L15":"tcm_knowledge","L16":"tcm_assessment"}

_client = None
_model = None
_ready = False
_reindex_lock = Lock()
_rag_cache_stats = {"embedding_hits": 0, "embedding_misses": 0, "search_hits": 0, "search_misses": 0}

def _c():
    global _client
    if _client is None:
        from pymilvus import MilvusClient
        _client = MilvusClient(uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}")
    return _client

def _m():
    global _model, DIM
    if _model is None:
        try:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")  # 禁止联网检查
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(RAG_MODEL, device="cpu")
            # 自动检测模型输出维度
            test_vec = _model.encode(["test"], show_progress_bar=False)
            actual_dim = test_vec.shape[1]
            if actual_dim != DIM:
                logger.info("RAG model dims changed: %d → %d (model: %s)", DIM, actual_dim, RAG_MODEL)
                DIM = actual_dim
        except Exception:
            from sklearn.feature_extraction.text import TfidfVectorizer
            vec = TfidfVectorizer(max_features=DIM)
            class _TF: pass
            _TF.encode = staticmethod(lambda texts, **kw: np.pad(
                vec.fit_transform(texts).toarray(), ((0,0),(0,DIM-vec.fit_transform(texts).toarray().shape[1])))[:,:DIM].astype(np.float32))
            _model = _TF()
    return _model

def _enc(texts):
    """编码文本为向量, 带 LRU 缓存 (相同查询秒回)。"""
    if isinstance(texts, str):
        texts = [texts]
    # 单查询走缓存
    if len(texts) == 1:
        key = hashlib.md5(texts[0].encode("utf-8")).hexdigest()
        if key in _enc_cache:
            _enc_cache.move_to_end(key)
            return _enc_cache[key]
        from ..services.runtime_cache import get_runtime_cache
        distributed = get_runtime_cache().get_json(f"rag:embedding:{RAG_MODEL}:{DIM}:{key}")
        if isinstance(distributed, list) and distributed:
            _rag_cache_stats["embedding_hits"] += 1
            _enc_cache[key] = distributed
            return distributed
        _rag_cache_stats["embedding_misses"] += 1
    v = _m().encode(texts, show_progress_bar=False)
    result = v.tolist() if hasattr(v, "tolist") else v.tolist()
    if len(texts) == 1:
        _enc_cache[key] = result
        if len(_enc_cache) > _ENC_CACHE_MAX:
            _enc_cache.popitem(last=False)  # LRU 淘汰
        from ..services.runtime_cache import get_runtime_cache
        get_runtime_cache().set_json(f"rag:embedding:{RAG_MODEL}:{DIM}:{key}", result, RAG_EMBEDDING_CACHE_TTL)
    return result

def _base():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

LOCALS = ["source","category","topic","disease_id","department","version","indexed_at"]

def _milvus_rows(docs, vecs):
    return [{"id": i, "vector": vecs[i], "text": doc["text"], **{key: doc[key] for key in LOCALS}}
            for i, doc in enumerate(docs)]


def collection_row_count(collection_name: str) -> int:
    """Return the durable Milvus row count across supported client versions."""
    stats = _c().get_collection_stats(collection_name)
    return int(stats.get("row_count", 0))


def _index_revision() -> str:
    """Use an index revision in every retrieval key to make reindex invalidation atomic."""
    from ..services.runtime_cache import get_runtime_cache

    cache = get_runtime_cache()
    revision = cache.get_text("rag:index:revision")
    if revision is None:
        revision = "1"
        cache.set_text("rag:index:revision", revision, 31_536_000)
    return revision


def _record_reindex_metadata(indexed: dict[str, int]) -> None:
    from ..services.runtime_cache import get_runtime_cache

    cache = get_runtime_cache()
    revision = str(cache.increment("rag:index:revision"))
    cache.set_json(
        "rag:index:meta",
        {"revision": revision, "indexed_at": _time.time(), "documents": sum(indexed.values()), "layers": indexed},
        31_536_000,
    )


def rag_runtime_status() -> dict[str, Any]:
    """Operational state safe to expose to knowledge-base managers."""
    from ..services.runtime_cache import get_runtime_cache

    cache = get_runtime_cache()
    return {
        "index_revision": _index_revision(),
        "last_reindex": cache.get_json("rag:index:meta"),
        "cache": cache.status(),
        "query_cache_ttl_seconds": RAG_SEARCH_CACHE_TTL,
        "embedding_cache_ttl_seconds": RAG_EMBEDDING_CACHE_TTL,
        "model": RAG_MODEL,
        "dimension": DIM,
        "process_cache": dict(_rag_cache_stats),
    }

class RagIndexError(RuntimeError):
    """Raised when source knowledge cannot be safely rebuilt into Milvus."""


def _ensure(layers: Iterable[str] | None = None):
    global _ready
    # Resolve the embedding model before creating a collection.  A configured
    # non-default model can use 768/1024 dimensions instead of MiniLM's 384.
    _m()
    c = _c()
    selected_layers = list(layers or LAYERS)
    for layer in selected_layers:
        name = LAYERS[layer]
        if not c.has_collection(name):
            c.create_collection(
                collection_name=name,
                dimension=DIM,
                metric_type="COSINE",
                enable_dynamic_field=True,
            )
    _ready = True

def _text(value: Any) -> str:
    return str(value or "").strip()


def _document(*, text: str, source: str, category: str, topic: str, now: float,
              disease_id: str = "", department: str = "") -> dict[str, Any]:
    if not _text(topic) or not _text(text):
        raise RagIndexError(f"知识条目缺少 topic 或 content（来源: {source}）")
    return {
        "text": _text(text), "source": source, "category": category,
        "topic": _text(topic), "disease_id": _text(disease_id),
        "department": _text(department), "version": "2026-07-20", "indexed_at": now,
    }


def build_index_documents() -> dict[str, list[dict[str, Any]]]:
    """Load and validate every RAG source before any collection is changed."""
    now = _time.time()
    source_path = os.path.join(_base(), "config", "clinical_knowledge.json")
    with open(source_path, encoding="utf-8") as source_file:
        kn = json.load(source_file)
    if not isinstance(kn, dict):
        raise RagIndexError("clinical_knowledge.json 顶层必须是对象")

    def generic(section: str, layer: str, source: str, category: str, *, disease: bool = False):
        documents = []
        for item in kn.get(section, []):
            if not isinstance(item, dict):
                raise RagIndexError(f"{section} 包含非对象条目")
            topic = _text(item.get("topic"))
            content = _text(item.get("content"))
            documents.append(_document(
                text=f"{topic}. {content}", source=source, category=_text(item.get("category")) or category,
                topic=topic, disease_id=_text(item.get("disease_id")) if disease else "", now=now,
            ))
        return documents

    documents: dict[str, list[dict[str, Any]]] = {
        "L1": [], "L2": generic("disease_keypoints", "L2", "disease_keypoint", "疾病要点", disease=True),
        "L3": [], "L4": [], "L5": [],
        "L6": [], "L7": generic("emergency_protocols", "L7", "emergency_protocol", "急症处置"),
        "L8": generic("nursing_protocols", "L8", "nursing_protocol", "护理操作规程"),
        "L9": [],
    }
    for item in kn.get("scoring_rules", []):
        documents["L1"].append(_document(
            text=f"{_text(item.get('topic'))}. {_text(item.get('content'))}", source="scoring_rules",
            category=_text(item.get("category")) or "临床评分", topic=_text(item.get("topic")), now=now,
        ))

    tpl_dir = os.path.join(_base(), "src", "zhenhu", "inpatient", "disease_templates")
    for file_path in glob.glob(os.path.join(tpl_dir, "*.json")):
        with open(file_path, encoding="utf-8") as template_file:
            template = json.load(template_file)
        disease_id = _text(template.get("disease_id")) or os.path.basename(file_path).removesuffix(".json")
        discharge = "; ".join(_text(item.get("description") or item.get("condition")) for item in template.get("discharge_criteria", [])[:3] if isinstance(item, dict))
        complications = "; ".join(_text(item.get("complication")) for item in template.get("complication_monitoring", [])[:3] if isinstance(item, dict))
        name = _text(template.get("name")) or disease_id
        department = _text(template.get("department"))
        documents["L3"].append(_document(
            text=f"{name} [{department}]. 出院标准: {discharge}. 并发症: {complications}",
            source="disease_template", category="病种模板", topic=name, disease_id=disease_id,
            department=department, now=now,
        ))

    from .constants import DEPT_CHECKLIST
    for department, items in DEPT_CHECKLIST.items():
        documents["L4"].append(_document(
            text=f"{department} 护理清单: {'; '.join(_text(item) for item in items)}",
            source="dept_protocol", category="护理清单", topic=f"{department}护理清单",
            department=department, now=now,
        ))

    for item in kn.get("drug_interactions", []):
        if not isinstance(item, dict):
            raise RagIndexError("drug_interactions 包含非对象条目")
        # Older entries use pair/risk/severity/recommendation; newer curated
        # entries follow the documented topic/category/content contract.
        topic = _text(item.get("pair")) or _text(item.get("topic"))
        structured = [
            _text(item.get("pair")), _text(item.get("risk")),
            _text(item.get("severity")), _text(item.get("recommendation")),
        ]
        text = _text(item.get("content")) or ". ".join(
            label + value for label, value in zip(("药物相互作用: ", "风险: ", "严重度: ", "建议: "), structured) if value
        )
        documents["L5"].append(_document(
            text=text, source="drug_interaction", category=_text(item.get("category")) or "用药安全",
            topic=topic, now=now,
        ))

    for item in kn.get("lab_reference", []):
        if not isinstance(item, dict):
            raise RagIndexError("lab_reference 包含非对象条目")
        test = _text(item.get("test")) or _text(item.get("topic"))
        content = _text(item.get("content")) or (
            f"参考值: {_text(item.get('range'))}. 危急值: {_text(item.get('critical_low'))}-{_text(item.get('critical_high'))}. "
            f"临床意义: {_text(item.get('clinical_significance'))}"
        )
        documents["L6"].append(_document(text=f"{test}. {content}", source="lab_reference", category="检验参考", topic=test, now=now))

    for section in ("discharge_education", "patient_medication", "self_care"):
        for item in kn.get(section, []):
            if not isinstance(item, dict):
                raise RagIndexError(f"{section} 包含非对象条目")
            documents["L9"].append(_document(
                text=f"{_text(item.get('topic'))}. {_text(item.get('content'))}", source="patient_education",
                category="患者知识", topic=_text(item.get("topic")),
                disease_id=_text(item.get("disease_id")), now=now,
            ))

    for section, layer, source, category in [
        ("surgical_protocols", "L10", "surgical_protocol", "外科协议"),
        ("medication_dosing", "L11", "medication_dosing", "药物剂量"),
        ("infection_control", "L12", "infection_control", "感染控制"),
        ("nutrition_support", "L13", "nutrition_support", "营养支持"),
        ("obgyn_basics", "L14", "obgyn_basics", "妇产基础"),
        ("tcm_knowledge", "L15", "tcm_knowledge", "中医知识"),
        ("tcm_assessment", "L16", "tcm_assessment", "中医评估"),
    ]:
        documents[layer] = generic(section, layer, source, category)
    return documents


def expected_document_counts() -> dict[str, int]:
    return {layer: len(documents) for layer, documents in build_index_documents().items()}


def _reset_collections(layers: Iterable[str]) -> None:
    """A full rebuild must remove stale dynamic fields and stale source rows."""
    global _ready
    c = _c()
    selected_layers = list(layers)
    for layer in selected_layers:
        collection = LAYERS[layer]
        if c.has_collection(collection):
            c.drop_collection(collection)
    _ready = False
    _ensure(selected_layers)


def index_all(layers: Iterable[str] | None = None) -> dict[str, int]:
    # Collection replacement is destructive. Only one rebuild may prepare,
    # drop, and repopulate Milvus collections at a time.
    if not _reindex_lock.acquire(blocking=False):
        raise RagIndexError("RAG_REINDEX_IN_PROGRESS: 知识库索引正在重建，请稍后刷新状态")
    try:
        return _index_all(layers)
    finally:
        _reindex_lock.release()


def _index_all(layers: Iterable[str] | None = None) -> dict[str, int]:
    selected_layers = list(layers or LAYERS)
    invalid_layers = sorted(set(selected_layers) - set(LAYERS))
    if invalid_layers:
        raise RagIndexError(f"未知知识层: {', '.join(invalid_layers)}")

    # Build every source document and embedding before changing Milvus.  Model
    # loading or malformed source data must never empty an otherwise usable
    # collection set.
    all_documents = build_index_documents()
    prepared: dict[str, tuple[list[dict[str, Any]], Any]] = {}
    try:
        for layer in selected_layers:
            documents = all_documents[layer]
            prepared[layer] = (
                documents,
                _enc([document["text"] for document in documents]) if documents else [],
            )
    except Exception as exc:
        raise RagIndexError(f"向量准备失败，未修改现有索引: {type(exc).__name__}") from exc

    indexed: dict[str, int] = {}
    for layer in selected_layers:
        documents, vectors = prepared[layer]
        try:
            # Replace one layer at a time. A failure can therefore never erase
            # the layers that have not yet begun rebuilding.
            _reset_collections([layer])
            collection = LAYERS[layer]
            client = _c()
            if documents:
                client.insert(collection, _milvus_rows(documents, vectors))
            client.flush(collection_name=collection)
            actual = collection_row_count(collection)
            if actual != len(documents):
                raise RagIndexError(f"写入校验失败，期望 {len(documents)} 条，实际 {actual} 条")
            indexed[layer] = len(documents)
        except RagIndexError:
            raise
        except Exception as exc:
            raise RagIndexError(f"{layer} 重建失败: {type(exc).__name__}: {exc}") from exc

    _record_reindex_metadata(indexed)
    logger.info("RAG: %d documents rebuilt across %d layers", sum(indexed.values()), len(selected_layers))
    return indexed

def _selected_layers(layer: str | Iterable[str] | None) -> list[str]:
    if layer is None:
        return list(LAYERS)
    requested = [layer] if isinstance(layer, str) else list(layer)
    invalid = sorted(set(requested) - set(LAYERS))
    if invalid:
        raise ValueError(f"Unknown RAG layers: {', '.join(invalid)}")
    return requested


async def search(query: str, layer: str | Iterable[str] | None = None, top_k: int = 5,
                 disease_id: str | None = None, department: str | None = None) -> list[dict]:
    normalized_query = query.strip()
    if not normalized_query:
        return []
    selected_layers = _selected_layers(layer)
    top_k = max(1, min(int(top_k), 20))
    cache_payload = {
        "revision": _index_revision(), "query": normalized_query, "layers": selected_layers,
        "top_k": top_k, "disease_id": disease_id or "", "department": department or "",
    }
    cache_digest = hashlib.sha256(json.dumps(cache_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    from ..services.runtime_cache import get_runtime_cache
    cached = get_runtime_cache().get_json(f"rag:search:{cache_digest}")
    if isinstance(cached, list):
        _rag_cache_stats["search_hits"] += 1
        return cached
    _rag_cache_stats["search_misses"] += 1

    _ensure(selected_layers); c=_c(); qv=_enc([normalized_query])[0]
    flt=[]; 
    if disease_id: flt.append(f'disease_id=="{disease_id}"')
    if department: flt.append(f'department=="{department}"')
    colls=[LAYERS[item] for item in selected_layers]
    all_hits=[]
    for cn in colls:
        try:
            res=c.search(cn,[qv],limit=min(top_k,5),filter=" and ".join(flt) if flt else None,
                         output_fields=["source","category","topic","disease_id","department","version","indexed_at","text"])
            if res and res[0]:
                for hit in res[0]:
                    e=hit.get("entity",{})
                    lk=[k for k,v in LAYERS.items() if v==cn]
                    all_hits.append({"layer":lk[0]if lk else cn,"score":round(hit.get("distance",0),4),
                                     "source":e.get("source",""),"topic":e.get("topic",""),"category":e.get("category",""),
                                     "disease_id":e.get("disease_id",""),"department":e.get("department",""),
                                     "version":e.get("version",""),"indexed_at":e.get("indexed_at"),
                                     "text":e.get("text","")[:300]})
        except Exception as ex: logger.warning("RAG %s: %s",cn,ex)
    all_hits.sort(key=lambda x:x["score"],reverse=True)
    result = all_hits[:top_k]
    get_runtime_cache().set_json(f"rag:search:{cache_digest}", result, RAG_SEARCH_CACHE_TTL)
    return result

async def search_by_disease(disease_id:str,top_k:int=3)->list[dict]:
    r=await search(disease_id,layer="L2",top_k=top_k,disease_id=disease_id)
    if len(r)<top_k: r+=await search(disease_id,layer="L3",top_k=top_k-len(r),disease_id=disease_id)
    return r

def get_rag_stats()->dict:
    c=_c(); s={}
    for l,n in LAYERS.items():
        try:
            if c.has_collection(n): s[l]={"collection":n,"rows":collection_row_count(n)}
        except: s[l]={"collection":n,"rows":0}
    s["model_dim"]=DIM; s["milvus"]=f"{MILVUS_HOST}:{MILVUS_PORT}"
    return s
