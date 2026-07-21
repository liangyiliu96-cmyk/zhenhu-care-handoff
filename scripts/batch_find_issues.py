"""批量全链路测试 — 8剩余病种，DOCTOR_AUTO_APPROVE=false，快速找出异常"""
import os, sys, asyncio, json

os.environ["SKIP_BRIDGE"] = "true"
os.environ["DOCTOR_AUTO_APPROVE"] = "false"
os.environ["GRAPH_MODE"] = "classic"
os.environ["APP_ENV"] = "dev"
PROJ_SRC = os.path.join(os.path.dirname(__file__), "..", "services", "inpatient-ward", "src")
sys.path.insert(0, PROJ_SRC)

from zhenhu.inpatient.routes.patient_fixtures import PATIENTS
from zhenhu.inpatient.agent.loop import get_patient_loop, cleanup_patient_loop
from zhenhu.inpatient.agent.nodes import load_template
from zhenhu.inpatient.routes.state_store import set_state, get_state, update_state

RUN = ["pat-cad-001","pat-stroke-001","pat-ckd-001","pat-aki-001",
       "pat-gi_bleeding-001","pat-hyperthyroidism-001","pat-post_surgery-001","pat-tumor_chemo-001"]

issues = []
stats = []

for pk in RUN:
    p = PATIENTS[pk]
    disease = p["disease_id"]
    name = p["name"]
    
    try:
        loop = get_patient_loop(pk)
        state = loop.gen_input("new_admission")
        state["patient_id"] = pk
        for k in ["patient_data", "patient_history", "allergies", "lab_results"]:
            state[k] = p.get(k, [])
        state["disease_template"] = load_template(disease)
        
        result = asyncio.run(loop.plan_turn(state))
        checkpoints = []
        
        # Handle admission checkpoint
        if isinstance(result, dict) and result.get("status") == "pending_review":
            checkpoints.append(result.get("payload", {}).get("type", "?"))
            s = loop._current_state or state
            s["doctor_confirm_status"] = "approved"
            s.pop("pending_review", None)
            s.pop("interrupt_pending", None)
            set_state(pk, s)
            result = asyncio.run(loop.plan_turn(s))
        
        chain0 = len(result.get("document_chain", [])) if isinstance(result, dict) else 0
        if isinstance(result, dict) and "phase" in result:
            set_state(pk, result)
        
        # Monitoring rounds
        vitals = list(p["vital_signs_sequence"])
        discharged = False
        rounds_used = 0
        last_round = 0
        
        for i, vs in enumerate(vitals[:10]):
            current = get_state(pk) or result
            vss = list(current.get("vital_signs", []) or []) + [vs]
            update_state(pk, {"vital_signs": vss, "vital_signs_count": len(vss)})
            current = get_state(pk)
            tr = asyncio.run(loop.plan_turn(current))
            
            is_review = isinstance(tr, dict) and tr.get("status") == "pending_review"
            is_state = isinstance(tr, dict) and "phase" in tr and "status" not in tr
            
            if is_review:
                rtype = tr.get("payload", {}).get("type", "?")
                checkpoints.append(rtype)
                s = get_state(pk) or loop._current_state or current
                # Clear + approve
                if rtype == "doctor_confirm":
                    s["doctor_confirm_status"] = "approved"
                elif rtype == "med_confirm":
                    s["med_confirm_status"] = "approved"
                elif rtype == "discharge_sign":
                    s["discharge_sign_status"] = "signed"
                s.pop("pending_review", None)
                s.pop("interrupt_pending", None)
                set_state(pk, s)
                tr = asyncio.run(loop.plan_turn(s))
            
            if is_state:
                set_state(pk, tr)
                phase = tr.get("phase", "")
                last_round = tr.get("round_count", 0)
                rounds_used = i + 1
                if phase in ("discharge", "confirm", "handoff", "review"):
                    discharged = True
                    result = tr
                    break
                result = tr
        
        final = get_state(pk) or result
        chain = final.get("document_chain", [])
        hc = len(final.get("handoff_items", []) or [])
        
        # Anomaly detection
        anomalies = []
        if chain0 == 0:
            anomalies.append("empty admission chain")
        if not discharged:
            anomalies.append(f"not discharged after {rounds_used} rounds")
        if rounds_used <= 1 and discharged:
            anomalies.append(f"immediate discharge (1 round)")
        if last_round == 0 and discharged:
            anomalies.append("round_count=0 at discharge")
        if hc == 0 and discharged:
            anomalies.append("empty handoff")
        if "discharge_signed" not in chain and discharged:
            anomalies.append("missing discharge_signed")
        
        status = "ISSUES" if anomalies else "OK"
        stats.append(f"  {status:6s} {name[:8]:8s} {disease:16s} cps={len(checkpoints)} rounds={rounds_used} docs={chain0}->{len(chain)} handoff={hc} round={last_round} {anomalies}")
        
        if anomalies:
            issues.append({"patient": pk, "name": name, "disease": disease, "anomalies": anomalies, "chain": chain, "checkpoints": checkpoints})
        
    except Exception as e:
        stats.append(f"  CRASH   {name[:8]:8s} {disease:16s} {str(e)[:80]}")
        issues.append({"patient": pk, "name": name, "disease": disease, "anomalies": [f"CRASH: {e}"]})
    finally:
        cleanup_patient_loop(pk)

print("\n=== 批量全链路结果 ===\n")
for s in stats:
    print(s)

if issues:
    print(f"\n=== {len(issues)} patients with issues ===")
    for iss in issues:
        print(f"\n  {iss['patient']} {iss['name']} ({iss['disease']}):")
        for a in iss['anomalies']:
            print(f"    - {a}")
        print(f"    Checkpoints: {iss['checkpoints']}")
        print(f"    Chain: {iss['chain'][:8]}...{iss['chain'][-3:]}")
else:
    print("\nAll patients passed without issues!")
