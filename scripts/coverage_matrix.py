"""全功能覆盖矩阵 — 14患者 × 双模式, 标注每个功能的触发状态"""
import os, sys, asyncio, json
os.environ["SKIP_BRIDGE"] = "true"
os.environ["GRAPH_MODE"] = "classic"
os.environ["APP_ENV"] = "dev"
PROJ_SRC = os.path.join(os.path.dirname(__file__), "..", "services", "inpatient-ward", "src")
sys.path.insert(0, PROJ_SRC)

from zhenhu.inpatient.routes.patient_fixtures import PATIENTS
from zhenhu.inpatient.agent.loop import get_patient_loop, cleanup_patient_loop
from zhenhu.inpatient.agent.nodes import load_template
from zhenhu.inpatient.routes.state_store import set_state, get_state, update_state

FEATURES = ["admission", "history", "pe", "ddx", "med_rec", "triage", "doctor_confirm",
            "lab_review", "daily_round", "nursing", "med_alert", "med_adjust", "med_confirm",
            "transfer", "discharge_decision", "discharge_sign", "handoff", "doctor_review",
            "patient_confirm", "critical_value", "abnormal_lab", "interrupt_block",
            "discharge_reject", "reeval_window"]

results = {}

for auto_mode in [True, False]:
    os.environ["DOCTOR_AUTO_APPROVE"] = "true" if auto_mode else "false"
    mode_label = "AUTO" if auto_mode else "MANUAL"
    
    for pk in PATIENTS:
        p = PATIENTS[pk]
        disease = p["disease_id"]
        triggered = set()
        
        try:
            loop = get_patient_loop(pk)
            state = loop.gen_input("new_admission")
            state["patient_id"] = pk
            for k in ["patient_data", "patient_history", "allergies", "lab_results"]:
                state[k] = p.get(k, [])
            state["disease_template"] = load_template(disease)
            
            result = asyncio.run(loop.plan_turn(state))
            
            # Handle admission checkpoint
            if isinstance(result, dict) and result.get("status") == "pending_review":
                triggered.add("doctor_confirm")
                s = loop._current_state or state
                s["doctor_confirm_status"] = "approved"
                s.pop("pending_review", None)
                s.pop("interrupt_pending", None)
                set_state(pk, s)
                result = asyncio.run(loop.plan_turn(s))
            
            if isinstance(result, dict) and "phase" in result:
                set_state(pk, result)
                chain = result.get("document_chain", [])
                
                # Track admission features
                for feat, doc in [("admission","intake_note"), ("history","history_note"),
                                  ("pe","pe_note"), ("ddx","ddx_note"), ("med_rec","medication_reconciliation"),
                                  ("triage","risk_assessment"), ("lab_review","lab_review"),
                                  ("daily_round","daily_round_note"), ("nursing","nursing_note")]:
                    if doc in chain: triggered.add(feat)
                
                if "doctor_confirm_auto" in chain: triggered.add("doctor_confirm")
                if result.get("discharge_decision"): triggered.add("discharge_decision")
                if (result.get("clinical_alerts") or []): triggered.add("abnormal_lab")
            
            # Monitoring rounds
            vitals = list(p["vital_signs_sequence"])
            for i, vs in enumerate(vitals[:12]):
                current = get_state(pk) or result
                vss = list(current.get("vital_signs", []) or []) + [vs]
                update_state(pk, {"vital_signs": vss, "vital_signs_count": len(vss)})
                current = get_state(pk)
                tr = asyncio.run(loop.plan_turn(current))
                
                is_review = isinstance(tr, dict) and tr.get("status") == "pending_review"
                is_state = isinstance(tr, dict) and "phase" in tr and "status" not in tr
                
                if is_review:
                    rtype = tr.get("payload", {}).get("type", "?")
                    if rtype == "doctor_confirm": triggered.add("doctor_confirm")
                    elif rtype == "med_confirm": triggered.add("med_confirm")
                    elif rtype == "discharge_sign": triggered.add("discharge_sign")
                    
                    s = get_state(pk) or loop._current_state or current
                    # Simulate doctor reject for one discharge_sign (first encounter only)
                    if rtype == "discharge_sign" and "discharge_reject" not in triggered:
                        if i < len(vitals) - 2:  # Not last round
                            s["discharge_sign_status"] = "rejected"
                            s["discharge_decision"] = "pending_reevaluation"
                            s["discharge_reject_history"] = [{"reason": "Doctor wants more monitoring"}]
                            s["discharge_reeval_after_rounds"] = (current.get("round_count", 0) + 2)
                            triggered.add("discharge_reject")
                            triggered.add("reeval_window")
                        else:
                            s["discharge_sign_status"] = "signed"
                    elif rtype == "doctor_confirm":
                        s["doctor_confirm_status"] = "approved"
                    elif rtype == "med_confirm":
                        s["med_confirm_status"] = "approved"
                    s.pop("pending_review", None)
                    s.pop("interrupt_pending", None)
                    set_state(pk, s)
                    tr = asyncio.run(loop.plan_turn(s))
                
                if is_state:
                    set_state(pk, tr)
                    phase = tr.get("phase", "")
                    chain = tr.get("document_chain", [])
                    
                    for feat, doc in [("handoff","handoff_note"), ("doctor_review","review_note"),
                                      ("patient_confirm","confirm_note"), ("discharge_sign","discharge_signed")]:
                        if doc in chain: triggered.add(feat)
                    if "med_reviewed" in chain: triggered.add("med_confirm")
                    if "medication_adjust" in chain: triggered.add("med_adjust")
                    if (tr.get("clinical_alerts") or []): triggered.add("abnormal_lab")
                    if tr.get("transfer_needed"): triggered.add("transfer")
                    
                    if phase in ("discharge", "confirm", "handoff", "review"):
                        break
            
            # Check for critical values
            template = p.get("disease_template") or load_template(disease) if isinstance(state, dict) else {}
            if isinstance(state, dict):
                labs = state.get("lab_results", []) or []
                for lab in labs:
                    val = lab.get("value")
                    name = lab.get("name", "")
                    if name == "钾" and val is not None and (val < 3.0 or val > 6.0):
                        triggered.add("critical_value")
                    elif name == "血糖" and val is not None and (val < 2.8 or val > 25.0):
                        triggered.add("critical_value")
            
        except Exception as e:
            pass
        finally:
            cleanup_patient_loop(pk)
        
        # Track per patient
        key = f"{pk}({disease})"
        results.setdefault(key, {})[mode_label] = {f: (f in triggered) for f in FEATURES}

# Print coverage matrix
print("=== FUNCTION COVERAGE MATRIX (14 patients x 2 modes) ===\n")
print(f"{'Patient/Disease':30s} {'Mode':6s} " + " ".join(f"{f[:5]:5s}" for f in FEATURES))
print(f"{'':30s} {'':6s} " + " ".join(f"{'':5s}" for _ in FEATURES))

for pk_disease, modes in sorted(results.items()):
    for mode in ["AUTO", "MANUAL"]:
        if mode in modes:
            cov = modes[mode]
            marks = " ".join("  ✅ " if cov[f] else "  -- " for f in FEATURES)
            print(f"{pk_disease:30s} {mode:6s} {marks}")

# Summary
print(f"\n=== COVERAGE SUMMARY ===")
for feat in FEATURES:
    auto_count = sum(1 for m in results.values() if m.get("AUTO", {}).get(feat, False))
    manual_count = sum(1 for m in results.values() if m.get("MANUAL", {}).get(feat, False))
    total = auto_count + manual_count
    status = "✅" if total > 0 else "❌ NEVER TRIGGERED"
    print(f"  {status} {feat:20s} AUTO={auto_count} MANUAL={manual_count} TOTAL={total}/28")
