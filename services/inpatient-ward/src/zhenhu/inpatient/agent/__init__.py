"""Agent框架 — v0.3 六组件统一。

公开 API:
  Graph:   inpatient_graph, InpatientState
  LLM:     safe_llm_invoke, deep_invoke, get_provider_for_node
  RAG:     rag_engine (Milvus 九层知识库), search_knowledge
  Nodes:   nodes, nodes_clinical, nodes_monitoring, nodes_admission, nodes_handoff
  Tools:   harness, assessments, medication_rules, clinical_external
  Config:  loop, config, prompts, constants, metrics
"""

from . import medication_rules  # noqa: F401
from . import assessments  # noqa: F401
from . import rag_engine   # noqa: F401  — v0.3 Milvus 知识引擎
from . import clinical_external  # noqa: F401  — v0.3 OpenAPI 管线
from .llm_utils import safe_llm_invoke, deep_invoke, get_provider_for_node  # noqa: F401  — v0.3 DeepAgent

try:
    from .graph import inpatient_graph, InpatientState  # noqa: F401
except ImportError:
    inpatient_graph = None
    InpatientState = None
