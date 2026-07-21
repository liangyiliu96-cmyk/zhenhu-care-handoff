"""全功能端到端测试 — 14患者全链路 + 8新路由 + 权限验证"""
import os, sys, asyncio, json
os.environ["SKIP_BRIDGE"] = "true"
os.environ["DOCTOR_AUTO_APPROVE"] = "true"
os.environ["GRAPH_MODE"] = "classic"
os.environ["APP_ENV"] = "dev"
PROJ = os.path.join(os.path.dirname(__file__), "..", "services", "inpatient-ward", "src")
sys.path.insert(0, PROJ)

from fastapi.testclient import TestClient
from zhenhu.inpatient.main import app
from zhenhu.inpatient.routes.patient_fixtures import PATIENTS
from zhenhu.inpatient.agent.loop import get_patient_loop, cleanup_patient_loop
from zhenhu.inpatient.agent.nodes import load_template
from zhenhu.inpatient.routes.state_store import set_state, get_state, update_state

client = TestClient(app)
issues = []

# ============================================
# Phase 1: 跑全14患者临床流程
# ============================================
print("Phase 1: 14 patients full clinical flow...")
clinical_ok = 0
for pk, p in PATIENTS.items():
    try:
        loop = get_patient_loop(pk)
        state = loop.gen_input("new_admission")
        state.update({"patient_id": pk, "patient_data": p.get("patient_data", {}),
                       "patient_history": p.get("patient_history", {}),
                       "allergies": p.get("allergies", []),
                       "lab_results": p.get("lab_results", []),
                       "disease_template": load_template(p["disease_id"])})
        result = asyncio.run(loop.plan_turn(state))
        if isinstance(result, dict) and result.get("status") == "pending_review":
            s = loop._current_state or state
            s["doctor_confirm_status"] = "approved"
            s.pop("pending_review", None)
            set_state(pk, s)
            result = asyncio.run(loop.plan_turn(s))
        if isinstance(result, dict) and "phase" in result:
            set_state(pk, result)
            chain = result.get("document_chain", [])
            if len(chain) >= 9:
                clinical_ok += 1
            else:
                issues.append(f"{pk}: short chain {len(chain)}")
        cleanup_patient_loop(pk)
    except Exception as e:
        issues.append(f"{pk} CRASH: {str(e)[:80]}")
        cleanup_patient_loop(pk)

print(f"  Clinical: {clinical_ok}/{len(PATIENTS)} OK")

# ============================================
# Phase 2: 跑多轮体征直到出院
# ============================================
print("Phase 2: Monitoring rounds (5 patients)...")
for pk in list(PATIENTS.keys())[:5]:
    p = PATIENTS[pk]
    loop = get_patient_loop(pk)
    state = loop.gen_input("new_admission")
    state.update({"patient_id": pk, "patient_data": p.get("patient_data", {}),
                   "patient_history": p.get("patient_history", {}),
                   "allergies": p.get("allergies", []),
                   "lab_results": p.get("lab_results", []),
                   "disease_template": load_template(p["disease_id"])})
    result = asyncio.run(loop.plan_turn(state))
    if isinstance(result, dict) and result.get("status") == "pending_review":
        s = loop._current_state or state
        s["doctor_confirm_status"] = "approved"
        s.pop("pending_review", None)
        set_state(pk, s)
        result = asyncio.run(loop.plan_turn(s))
    if isinstance(result, dict) and "phase" in result:
        set_state(pk, result)
    vitals = list(p["vital_signs_sequence"])
    for i, vs in enumerate(vitals[:6]):
        current = get_state(pk) or result
        vss = list(current.get("vital_signs", []) or []) + [vs]
        update_state(pk, {"vital_signs": vss})
        current = get_state(pk)
        tr = asyncio.run(loop.plan_turn(current))
        if isinstance(tr, dict) and "phase" in tr and "status" not in tr:
            set_state(pk, tr)
            if tr.get("phase") in ("discharge","confirm","handoff","review"):
                break
    cleanup_patient_loop(pk)
print("  Monitoring: done")

# ============================================
# Phase 3: 新路由功能测试
# ============================================
print("Phase 3: New routes...")

tests = {
    "ward_overview": lambda: client.get("/ward/overview"),
    "ward_alerts": lambda: client.get("/ward/alerts"),
    "ward_vitals": lambda: client.get("/ward/vitals"),
    "patients": lambda: client.get("/patients"),
    "patients_phase": lambda: client.get("/patients?phase=monitoring"),
    "patients_risk": lambda: client.get("/patients?risk_level=medium"),
    "patients_search": lambda: client.get("/patients?search=张"),
    "nurse_tasks": lambda: client.get("/nurse/tasks"),
    "reviews_pending": lambda: client.get("/reviews/pending"),
    "monitoring_overdue": lambda: client.get("/monitoring/overdue"),
}

for name, fn in tests.items():
    try:
        r = fn()
        if r.status_code == 200:
            data = r.json()
            d = data.get("data", {})
            total = d.get("total", "?")
            print(f"  {name:25s} => 200 total={total}")
            # Structural checks
            if name == "ward_overview" and "by_risk" not in d:
                issues.append(f"{name}: missing by_risk")
            if name == "patients" and "patients" not in d:
                issues.append(f"{name}: missing patients array")
            if "filters" not in r.text and name == "patients" and "?" in "?":
                pass  # optional
        else:
            issues.append(f"{name}: HTTP {r.status_code}")
            print(f"  {name:25s} => {r.status_code}")
    except Exception as e:
        issues.append(f"{name}: {str(e)[:60]}")

# ============================================
# Phase 4: Dashboard/Discharge summary  
# ============================================
print("Phase 4: Dashboard + Discharge summary...")
for pk in list(PATIENTS.keys())[:3]:
    r = client.get(f"/inpatient/{pk}/dashboard")
    if r.status_code == 200:
        d = r.json().get("data", {})
        has_vs = len(d.get("vital_trend", [])) > 0
        has_ddx = len(d.get("ddx_top3", [])) > 0
        print(f"  dashboard/{pk}: vs={has_vs} ddx={has_ddx}")
    else:
        issues.append(f"dashboard/{pk}: {r.status_code}")

    r = client.get(f"/inpatient/{pk}/discharge-summary")
    if r.status_code == 200:
        d = r.json().get("data", {})
        print(f"  discharge/{pk}: diag={d.get('primary_diagnosis','?')[:30]}")
    else:
        issues.append(f"discharge/{pk}: {r.status_code}")

# ============================================
# Phase 5: 权限验证
# ============================================
print("Phase 5: Auth verification...")
auth_tests = [
    ("/patients", "hacker", 403), ("/patients", "nurse", 200),
    ("/ward/overview", "guest", 403), ("/ward/overview", "doctor", 200),
    ("/nurse/tasks", "patient", 403), ("/nurse/tasks", "nurse", 200),
    ("/reviews/pending", "staff", 403),
    ("/monitoring/overdue", "hacker", 403),
]
for path, role, expect in auth_tests:
    r = client.get(path, headers={"x-role": role})
    if r.status_code != expect:
        issues.append(f"auth: {path} x-role={role} => {r.status_code} (expect {expect})")
print(f"  Auth: {len(auth_tests)} checks")

# ============================================
# Phase 6: Document chain integrity
# ============================================
print("Phase 6: Chain integrity...")
for pk in list(PATIENTS.keys())[:5]:
    state = get_state(pk)
    if state:
        chain = state.get("document_chain", [])
        has_dup = len(chain) != len(set(chain))
        if has_dup:
            dups = [d for d in chain if chain.count(d) > 1]
            issues.append(f"{pk}: duplicate docs {list(set(dups))}")
        if len(chain) > 0 and chain[0] != "intake_note":
            issues.append(f"{pk}: chain doesn't start with intake_note")
        if "discharge_signed" in chain and "confirm_note" not in chain:
            issues.append(f"{pk}: discharged without confirm_note")

# ============================================
# Report
# ============================================
print(f"\n{'='*60}")
if issues:
    print(f"ISSUES ({len(issues)}):")
    for i in issues:
        print(f"  - {i}")
else:
    print("ALL CLEAN — no issues found")
print(f"{'='*60}")
