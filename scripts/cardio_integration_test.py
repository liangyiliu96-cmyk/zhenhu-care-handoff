"""Cardio + 臻护 端到端全链路验证脚本。

验证:
1. Cardio Agent Graph 入院→出院→交接 全流程
2. Cardio → 臻护 knowledge-orchestrator 检索
3. Cardio → 臻护 fhir-adapter 患者查询
4. Cardio → 臻护 workflow-engine 创建病例
"""
import asyncio
import json
import sys
import urllib.request

sys.path.insert(0, r"D:\AI医疗赋能\cardio-inpatient-collab\backend\app\src")

# ── 1. 臻护 health check ──
print("1. 臻护三服务健康检查")
for name, port in [("workflow", 8100), ("knowledge", 8200), ("fhir", 8300)]:
    d = json.loads(urllib.request.urlopen(f"http://localhost:{port}/health", timeout=5).read())
    print(f"  {name}: {d['status']}")
print()

# ── 2. Cardio Agent Graph 全流程 ──
print("2. Cardio 入院全流程 Agent Graph")

from zhenhu.inpatient.agent.graph import inpatient_graph
from zhenhu.inpatient.agent.nodes import load_template

if inpatient_graph is None:
    print("  ❌ langgraph 未安装, 跳过 Agent 测试")
else:
    template = load_template("hypertension")
    initial = {
        "patient_id": "pat-demo-001",
        "disease_template": template,
        "phase": "admission",
        "vital_signs": [{"bp": "140/85"}, {"bp": "135/80"}, {"bp": "130/82"}, {"bp": "125/78"}, {"bp": "128/80"}, {"bp": "122/76"}],
        "risk_level": "low",
        "discharge_decision": None,
        "handoff_items": [],
        "document_chain": [],
        "event_type": "admission_start",
        "interrupt_pending": False,
    }
    result = asyncio.run(inpatient_graph.ainvoke(initial))
    print(f"  phase:         {result.get('phase')}")
    print(f"  risk_level:    {result.get('risk_level')}")
    print(f"  discharge:     {result.get('discharge_decision')}")
    print(f"  handoff_items: {len(result.get('handoff_items', []))} 条")
    print(f"  mdt_required:  {result.get('mdt_required', False)}")
    for item in result.get("handoff_items", []):
        print(f"    - [{item.get('type')}] {item.get('content', '')[:40]}")
print()

# ── 3. Cardio → 臻护 knowledge 检索 ──
print("3. Cardio → knowledge-orchestrator 检索")
q = "阿莫西林"  # URL safe ASCII keyword
try:
    import urllib.parse
    # 预置文档: drug-label-amoxicillin-clavulanate "阿莫西林克拉维酸钾"
    d = json.loads(urllib.request.urlopen(
        f"http://localhost:8200/knowledge/search?q={urllib.parse.quote('阿莫西林')}", timeout=5
    ).read())
    results = d.get("data", {}).get("results", [])
    print(f"  搜索'阿莫西林': {len(results)} 条结果")
    if results:
        r0 = results[0]
        print(f"  [{r0.get('score', 0):.2f}] {r0.get('text', '')[:60]}...")
    else:
        # fallback: 尝试英文搜索
        d2 = json.loads(urllib.request.urlopen(
            f"http://localhost:8200/knowledge/search?q=amoxicillin", timeout=5
        ).read())
        results2 = d2.get("data", {}).get("results", [])
        print(f"  搜索'amoxicillin': {len(results2)} 条结果")
except Exception as e:
    print(f"  ❌ {e}")
print()

# ── 4. Cardio → 臻护 fhir 患者查询 ──
print("4. Cardio → fhir-adapter 患者查询")
try:
    d = json.loads(urllib.request.urlopen("http://localhost:8300/fhir/Patient/pat-demo-001", timeout=5).read())
    name = d.get("data", {}).get("name", [{}])
    print(f"  患者: {name[0].get('text', '?') if name else '?'}")
    gender = d.get("data", {}).get("gender", "?")
    print(f"  性别: {gender}")
except Exception as e:
    print(f"  ❌ {e}")
print()

# ── 5. Cardio → 臻护 workflow 创建病例 ──
print("5. Cardio → workflow-engine 创建病例")
try:
    req = urllib.request.Request(
        "http://localhost:8100/cases",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"input_snapshot_id": "cardio-pat-demo-001"}).encode(),
    )
    d = json.loads(urllib.request.urlopen(req, timeout=5).read())
    case_id = d.get("data", {}).get("case_id", "NONE")
    state = d.get("data", {}).get("state", "NONE")
    print(f"  病例ID: {case_id}")
    print(f"  状态:   {state}")
    print(f"  ✅ 出院→臻护 bridge 打通" if case_id != "NONE" else "  ❌ 桥接失败")
except Exception as e:
    print(f"  ❌ {e}")

print("\n=== 全链路验证完成 ===")
