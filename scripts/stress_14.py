"""全量14患者压力测试 — MANUAL模式 + 拒签模拟"""
import os, sys, asyncio, json
os.environ["SKIP_BRIDGE"] = "true"
os.environ["DOCTOR_AUTO_APPROVE"] = "false"
os.environ["GRAPH_MODE"] = "classic"
os.environ["APP_ENV"] = "dev"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "inpatient-ward", "src"))

from zhenhu.inpatient.routes.patient_fixtures import PATIENTS
from zhenhu.inpatient.agent.loop import get_patient_loop, cleanup_patient_loop
from zhenhu.inpatient.agent.nodes import load_template
from zhenhu.inpatient.routes.state_store import set_state, get_state, update_state

anomalies = []

for pk in PATIENTS:
    p = PATIENTS[pk]
    disease = p["disease_id"]
    issues = []
    
    try:
        loop = get_patient_loop(pk)
        state = loop.gen_input("new_admission")
        state["patient_id"] = pk
        for k in ["patient_data","patient_history","allergies","lab_results"]:
            state[k] = p.get(k, [])
        state["disease_template"] = load_template(disease)
        
        result = asyncio.run(loop.plan_turn(state))
        cps = []
        
        if isinstance(result, dict) and result.get("status") == "pending_review":
            cps.append("adm")
            s = loop._current_state or state
            s["doctor_confirm_status"] = "approved"
            s.pop("pending_review",None); s.pop("interrupt_pending",None)
            set_state(pk, s)
            result = asyncio.run(loop.plan_turn(s))
        
        if isinstance(result, dict) and "phase" in result:
            chain0 = len(result.get("document_chain", []))
            if chain0 < 9:
                issues.append(f"short admission chain: {chain0} docs")
            set_state(pk, result)
            required = ["intake_note","history_note","pe_note","ddx_note","medication_reconciliation","risk_assessment","lab_review","daily_round_note","nursing_note"]
            missing = [d for d in required if d not in result.get("document_chain", [])]
            if missing: issues.append(f"missing admission docs: {missing}")
        
        vitals = list(p["vital_signs_sequence"])
        discharged = 0
        
        for i, vs in enumerate(vitals[:10]):
            current = get_state(pk) or result
            vss = list(current.get("vital_signs", []) or []) + [vs]
            update_state(pk, {"vital_signs": vss, "vital_signs_count": len(vss)})
            current = get_state(pk)
            tr = asyncio.run(loop.plan_turn(current))
            
            is_review = isinstance(tr, dict) and tr.get("status") == "pending_review"
            is_state = isinstance(tr, dict) and "phase" in tr and "status" not in tr
            
            if is_review:
                rtype = tr.get("payload",{}).get("type","?")
                cps.append(rtype)
                s = get_state(pk) or loop._current_state or current
                if rtype == "doctor_confirm": s["doctor_confirm_status"] = "approved"
                elif rtype == "med_confirm": s["med_confirm_status"] = "approved"
                elif rtype == "discharge_sign":
                    if i < len(vitals) - 2 and "reject" not in cps:
                        s["discharge_sign_status"] = "rejected"
                        s["discharge_decision"] = "pending_reevaluation"
                        s["discharge_reject_history"] = [{"reason":"Doctor wants more observation"}]
                        s["discharge_reeval_after_rounds"] = (current.get("round_count",0) + 2)
                        cps.append("REJECTED")
                    else:
                        s["discharge_sign_status"] = "signed"
                s.pop("pending_review",None); s.pop("interrupt_pending",None)
                set_state(pk, s)
                tr = asyncio.run(loop.plan_turn(s))
            
            if is_state:
                set_state(pk, tr)
                phase = tr.get("phase", "")
                chain = tr.get("document_chain", [])
                
                if phase in ("discharge","confirm","handoff","review"):
                    hl = len(tr.get("handoff_items", []) or [])
                    if hl == 0: issues.append("empty handoff at discharge")
                    if "discharge_signed" not in chain: issues.append("missing discharge_signed")
                    if "handoff_note" not in chain: issues.append("missing handoff_note")
                    discharged = i + 1
                    break
        
        if not discharged:
            issues.append(f"not discharged in {len(vitals)} rounds")
        
        if issues:
            anomalies.append({"patient": pk, "disease": disease, "issues": issues, "cps": cps})
    
    except Exception as e:
        anomalies.append({"patient": pk, "disease": p["disease_id"], "issues": [f"CRASH: {e}"]})
    finally:
        cleanup_patient_loop(pk)

print(f"=== {len(anomalies)} patients with issues out of {len(PATIENTS)} ===\n")
for a in anomalies:
    print(f"{a['patient']} ({a['disease']}): cps={a.get('cps',[])}")
    for iss in a['issues']:
        print(f"  - {iss}")

clean = [pk for pk in PATIENTS if pk not in [a['patient'] for a in anomalies]]
print(f"\nClean: {len(clean)}/{len(PATIENTS)}")
print(f"\nAll checkpoint patterns:")
for a in anomalies:
    print(f"  {a['patient']:25s} {a['cps']}")
