"""臻护后端集成测试 —— 三服务跨链路验证（阶段 0）。

验证核心跨服务能力：
  1. 三服务健康检查
  2. FHIR 患者数据脱敏
  3. 知识检索与生命周期
  4. 工作流核心链路（创建→分析→关闭）
  5. 知识反向阻断钩子
"""

import json
import urllib.request as http
from urllib.error import HTTPError

BASE = {
    "workflow": "http://localhost:8100",
    "knowledge": "http://localhost:8200",
    "fhir": "http://localhost:8300",
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


def main():
    global passed, failed

    print("=== 臻护后端集成测试（阶段 0）===\n")

    # ── 1. 服务健康检查 ──
    print("1. 三服务健康检查")
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

    # ── 6. chengjie ──
    total = passed + failed
    print(f"\n{'='*40}")
    print(f"  总计: {passed}/{total} 通过")
    if failed == 0:
        print("  ✅ 全部通过 — 三服务跨链路验证成功")
    else:
        print(f"  ⚠️  {failed} 项失败")
    print(f"{'='*40}")


if __name__ == "__main__":
    main()
