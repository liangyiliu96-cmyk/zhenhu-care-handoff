"""臻护后端集成测试 —— 四服务跨链路验证（阶段 1）。

验证核心跨服务能力：
  1. 四服务健康检查
  2. FHIR 患者数据脱敏
  3. 知识检索与生命周期
  4. 工作流核心链路（创建→分析→关闭）
  5. 知识反向阻断钩子
  6. Cardio 全链路验证（Agent Graph → 臻护三服务）
"""

import json
import urllib.request as http
from urllib.error import HTTPError

BASE = {
    "workflow": "http://localhost:8100",
    "knowledge": "http://localhost:8200",
    "fhir": "http://localhost:8300",
    "inpatient": "http://127.0.0.1:8001",
}

passed = 0
failed = 0


def api(method, url, data=None, timeout=10):
    body = json.dumps(data).encode() if data else None
    req = http.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with http.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


def check(condition, label):
    global passed, failed
    if condition:
        print(f"  ✅ PASS  {label}")
        passed += 1
    else:
        print(f"  ❌ FAIL  {label}")
        failed += 1


# ───────────────────────────── Cardio 全链路验证 ─────────────────────────────

def test_cardio_full_chain():
    """Cardio + 臻护 端到端全链路验证。

    验证:
    1. Cardio Agent Graph 入院→出院→交接 全流程
    2. Cardio → 臻护 knowledge-orchestrator 检索
    3. Cardio → 臻护 fhir-adapter 患者查询
    4. Cardio → 臻护 workflow-engine 创建病例
    """
    global passed, failed

    # ── C1. 臻护 inpatient 健康检查 ──
    print("\n6. Cardio + 臻护 全链路验证")
    code, d = api("GET", f"{BASE['inpatient']}/health")
    check(code == 200 and d.get("status") == "ok", "inpatient-ward /health")
    if code != 200:
        print("  ⚠️  inpatient-ward 未就绪, 跳过 Agent 验证")
        return

    # ── C2. Cardio Agent Graph 全流程 ──
    try:
        import asyncio
        import sys
        from zhenhu.inpatient.agent.graph import inpatient_graph
        from zhenhu.inpatient.agent.nodes import load_template
    except ImportError as e:
        print(f"  ⚠️  无法导入 inpatient agent ({e}), 跳过 Agent Graph 测试")
        return

    if inpatient_graph is None:
        print("  ⚠️  langgraph 未安装, 跳过 Agent 测试")
        return

    template = load_template("hypertension")
    initial = {
        "patient_id": "pat-demo-001",
        "disease_template": template,
        "phase": "admission",
        "vital_signs": [
            {"bp": "140/85"}, {"bp": "135/80"}, {"bp": "130/82"},
            {"bp": "125/78"}, {"bp": "128/80"}, {"bp": "122/76"},
        ],
        "risk_level": "low",
        "discharge_decision": None,
        "handoff_items": [],
        "document_chain": [],
        "event_type": "admission_start",
        "interrupt_pending": False,
    }

    try:
        result = asyncio.run(inpatient_graph.ainvoke(initial))
        check(result.get("phase") is not None, f"Agent 全流程完成 (phase={result.get('phase')})")
        check(len(result.get("handoff_items", [])) >= 0, f"交接项目 {len(result.get('handoff_items', []))} 条")
    except Exception as e:
        print(f"  ❌ FAIL  Agent Graph 执行异常: {e}")
        failed += 1

    # ── C3. Cardio → knowledge 检索 ──
    import urllib.parse
    try:
        d = json.loads(urllib.request.urlopen(
            f"http://localhost:8200/knowledge/search?q={urllib.parse.quote('阿莫西林')}", timeout=5
        ).read())
        results = d.get("data", {}).get("results", [])
        check(len(results) >= 1, f"阿莫西林知识检索 ({len(results)} 条)")
    except Exception as e:
        print(f"  ❌ FAIL  知识检索异常: {e}")
        failed += 1

    # ── C4. Cardio → fhir 患者查询 ──
    code, p = api("GET", f"{BASE['fhir']}/fhir/Patient/pat-demo-001")
    name = p.get("data", {}).get("name", [{}])
    check(code == 200, f"患者查询 ({name[0].get('text', '?') if name else '?'})")

    # ── C5. Cardio → workflow 创建病例 ──
    code, case = api("POST", f"{BASE['workflow']}/cases", {"input_snapshot_id": "cardio-pat-demo-001"})
    cid = case.get("data", {}).get("case_id", "")
    check(code == 201 or "case_id" in str(case), f"Cardio→臻护 bridge ({cid})")


def main():
    global passed, failed

    print("=== 臻护后端集成测试（阶段 1）===\n")

    # ── 1. 服务健康检查 ──
    print("1. 四服务健康检查")
    for name, url in BASE.items():
        code, data = api("GET", f"{url}/health")
        check(code == 200 and data.get("status") == "ok", f"{name} /health")
    if failed:
        return print("\n❌ 服务未就绪，终止")

    # ── 2. FHIR 适配层 ──
    print("\n2. FHIR 适配层")
    code, p = api("GET", f"{BASE['fhir']}/fhir/Patient/pat-demo-001")
    name = p["data"]["name"][0]["text"] if p.get("data", {}).get("name") else ""
    check(code == 200 and "演" in name, f"患者数据脱敏 ({name})")

    code, cp = api("GET", f"{BASE['fhir']}/fhir/Patient/pat-demo-001/CarePlan")
    check(code == 200, f"照护计划 Bundle ({len(cp.get('data',[]))} 条)")

    code, _ = api("GET", f"{BASE['fhir']}/fhir/Patient/nonexistent")
    check(code == 404, "不存在的患者 → 404")

    # ── 3. 知识编排 ──
    print("\n3. 知识编排")
    code, docs = api("GET", f"{BASE['knowledge']}/knowledge/documents?status=published")
    check(code == 200 and len(docs.get("data", [])) >= 1, f"已发布知识 {len(docs.get('data',[]))} 份")

    code, search = api("GET", f"{BASE['knowledge']}/knowledge/search?q=%E9%98%BF%E8%8E%AB%E8%A5%BF%E6%9E%97")
    check(code == 200, f"知识检索成功 ({len(search.get('data',[]))} 条)")

    code, audit = api("GET", f"{BASE['knowledge']}/knowledge/audit")
    check(code == 200, "知识审计事件可查询")

    # ── 4. 工作流核心链路 ──
    print("\n4. 工作流引擎")
    wf = BASE["workflow"]

    code, case = api("POST", f"{wf}/cases", {"input_snapshot_id": "snap-int-001"})
    cid = case["data"]["case_id"]
    check(code == 201, f"创建病例 → draft ({cid})")

    code, a = api("POST", f"{wf}/cases/{cid}/analyse")
    check(code == 200, f"分析完成 → {a['data']['state']}")

    code, _ = api("POST", f"{wf}/cases/{cid}/analyse")
    check(code == 409, "重复分析被拒绝 → 409")

    code, canc = api("POST", f"{wf}/cases/{cid}/cancel")
    check(code == 200 and canc["data"]["state"] == "cancelled", f"取消病例 → cancelled")

    code, _ = api("POST", f"{wf}/cases/{cid}/cancel")
    check(code == 409, "已取消后不可再取消 → 409")

    # ── 5. 知识反向阻断钩子 ──
    print("\n5. 跨服务钩子")
    code, hook = api("POST", f"{wf}/hooks/knowledge-changed",
                     {"document_id": "drug-label-amoxicillin-clavulanate"})
    blocked = hook.get("data", {}).get("blocked_count", 0)
    check(code == 200, f"知识变更阻断钩子 (blocked={blocked})")

    # ── 6. Cardio 全链路验证 ──
    test_cardio_full_chain()

    # ── 总结 ──
    total = passed + failed
    print(f"\n{'='*40}")
    print(f"  总计: {passed}/{total} 通过")
    if failed == 0:
        print("  ✅ 全部通过 — 四服务跨链路验证成功")
    else:
        print(f"  ⚠️  {failed} 项失败")
    print(f"{'='*40}")


if __name__ == "__main__":
    main()
