"""Agent框架 - LangGraph 住院协同编排。合并迁入。

导出 InpatientState 和 inpatient_graph(StateGraph 实例)。
若 langgraph 未安装则 graph 不可用, harness/bridge/tools 仍可独立使用。
P0-3: 导出 medication_rules 药物相互作用规则模块。
"""

from . import medication_rules  # noqa: F401
from . import assessments  # noqa: F401

try:
    from .graph import inpatient_graph, InpatientState  # noqa: F401
except ImportError:
    inpatient_graph = None
    InpatientState = None
