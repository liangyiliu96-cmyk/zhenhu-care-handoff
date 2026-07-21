"""医生介入全链路追踪 — COPD患者 刘德明，AUTO_APPROVE=OFF"""
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

pk = "pat-copd-001"
p = PATIENTS[pk]
SEP = chr(9472) * 70

print(f"\n{chr(128100)} {p['name']} | {p['disease_id']} | {p['description']}")
print(f"   吸烟: 20支/日x40年 | 煤矿工人30年 | GOLD III级")
print(f"   合并症: {p['patient_history']['comorbidities']}")
print(f"   用药: {p['patient_history']['medications']}")
print(f"   入院 SpO2: {p['vital_signs_sequence'][0]['spo2']}% | PaCO2: {p['vital_signs_sequence'][0]['paco2']} mmHg")
print()

loop = get_patient_loop(pk)
state = loop.gen_input("new_admission")
state["patient_id"] = pk
state["patient_data"] = p["patient_data"]
state["patient_history"] = p.get("patient_history", {})
state["allergies"] = p.get("allergies", [])
state["lab_results"] = p.get("lab_results", [])
state["disease_template"] = load_template(p["disease_id"])

# ==== first admission ====
print("First plan_turn (AUTO_APPROVE=OFF)...")
result = asyncio.run(loop.plan_turn(state))

if isinstance(result, dict) and result.get("status") == "pending_review":
    # graph accumulated state saved in loop._current_state by plan_turn
    payload = result.get("payload", {})
    print(f"\n{SEP}")
    print(f"  STOP  Checkpoint-1: Admission Confirmation")
    print(f"{SEP}")
    print(f"  Review type: {payload.get('type')}")
    print(f"  Risk level: {payload.get('risk_level')}")
    print(f"  Chief complaint: {payload.get('chief_complaint', 'N/A')[:100]}")
    print(f"  HPI narrative: {str(payload.get('hpi_narrative', ''))[:200]}")
    print(f"  PE narrative: {str(payload.get('pe_narrative', ''))[:200]}")
    print(f"  DDx: {[(d.get('diagnosis','?'), d.get('likelihood','?')) for d in (payload.get('ddx_list') or [])]}")
    print(f"  Allergies: {payload.get('allergies')}")
    print(f"  Clinical assessments: {json.dumps(payload.get('clinical_assessments', {}), ensure_ascii=False)[:200]}")
    print(f"  Clinical alerts: {payload.get('clinical_alerts', [])}")
    print(f"\n  DOCTOR: Reviewing clinical draft, approving admission")

    s = get_state(pk) or loop._current_state or state
    s["doctor_confirm_status"] = "approved"
    s.pop("pending_review", None)  # clear checkpoint
    s.pop("interrupt_pending", None)
    set_state(pk, s)
    result = asyncio.run(loop.plan_turn(s))
else:
    set_state(pk, result)

doc_chain = result.get("document_chain", []) if isinstance(result, dict) else []
print(f"  -> graph resume: phase={result.get('phase')} last_docs={' -> '.join(doc_chain[-5:])}")
print()

# ==== monitoring rounds ====
vitals = list(p["vital_signs_sequence"])
review_count = 0

for i, vs in enumerate(vitals):
    current = get_state(pk)
    if not current:
        current = result
    vss = list(current.get("vital_signs", []) or []) + [vs]
    update_state(pk, {"vital_signs": vss, "vital_signs_count": len(vss)})
    current = get_state(pk)
    tr = asyncio.run(loop.plan_turn(current))

    is_review = isinstance(tr, dict) and tr.get("status") == "pending_review"
    is_state = isinstance(tr, dict) and "phase" in tr and "status" not in tr

    if is_review:
        review_count += 1
        payload = tr.get("payload", {})
        rtype = payload.get("type", "?")
        print(f"{SEP}")

        if rtype == "med_confirm":
            print(f"  STOP  Checkpoint-2: Medication Confirmation #{review_count}")
            print(f"{SEP}")
            print(f"  Adjustments ({payload.get('adjustment_count', 0)}):")
            for m in (payload.get("medication_adjustments") or [])[:5]:
                print(f"    - {json.dumps(m, ensure_ascii=False)[:120]}")
            print(f"  Vital trend: {json.dumps(payload.get('vital_trend') or {}, ensure_ascii=False)[:200]}")
            print(f"  Abnormal labs: {payload.get('abnormal_labs')}")
            print(f"  AI remark: {str(payload.get('ai_remark', ''))[:150]}")
            print(f"  DDx TOP: {payload.get('ddx_top')}")
            print(f"  Alerts: {payload.get('recent_alerts', [])[:3]}")
            print(f"\n  DOCTOR: Approving medication adjustment")
            s = get_state(pk) or loop._current_state or current
            s["med_confirm_status"] = "approved"
            s.pop("pending_review", None)
            s.pop("interrupt_pending", None)
            set_state(pk, s)
            tr = asyncio.run(loop.plan_turn(s))

        elif rtype == "doctor_confirm":
            print(f"  STOP  Checkpoint-1: Admission Confirm #{review_count}")
            print(f"  DOCTOR: Approving")
            s = get_state(pk) or loop._current_state or current
            s["doctor_confirm_status"] = "approved"
            s.pop("pending_review", None)
            s.pop("interrupt_pending", None)
            set_state(pk, s)
            tr = asyncio.run(loop.plan_turn(s))

        elif rtype == "discharge_sign":
            print(f"  STOP  Checkpoint-3: Discharge Sign-off #{review_count}")
            print(f"{SEP}")
            print(f"  Decision: {payload.get('discharge_decision')}")
            print(f"  Handoff summary: {str(payload.get('handoff_summary', ''))[:200]}")
            print(f"  Handoff items ({payload.get('handoff_count', 0)}):")
            for h in (payload.get("handoff_items") or [])[:5]:
                print(f"    - [{h.get('type','?')}] {h.get('content', '')[:120]}")
            print(f"  Criteria: {json.dumps(payload.get('discharge_criteria_check', {}), ensure_ascii=False)[:200]}")
            print(f"  Vital trend: {json.dumps(payload.get('vital_trend') or {}, ensure_ascii=False)[:150]}")
            print(f"  Complication risks: {payload.get('complication_risks', [])}")
            print(f"  Latest SOAP: {json.dumps(payload.get('latest_soap') or {}, ensure_ascii=False)[:200]}")
            print(f"\n  DOCTOR: Signing discharge approval")
            s = get_state(pk) or loop._current_state or current
            s["discharge_sign_status"] = "signed"
            s.pop("pending_review", None)
            s.pop("interrupt_pending", None)
            set_state(pk, s)
            tr = asyncio.run(loop.plan_turn(s))
        else:
            print(f"  STOP  Unknown checkpoint: {rtype}")
            s = get_state(pk) or loop._current_state or current
            set_state(pk, s)
            tr = asyncio.run(loop.plan_turn(s))

    if isinstance(tr, dict) and "phase" in tr and "status" not in tr:
        set_state(pk, tr)
        phase = tr.get("phase", "")
        chain = tr.get("document_chain", [])
        new_docs = [d for d in chain if d not in doc_chain]
        v_info = f"SpO2={vs['spo2']}% RR={vs['respiratory_rate']} PaCO2={vs['paco2']}"
        print(f"  #{i+1} {v_info} -> phase={phase} round={tr.get('round_count')} dc={tr.get('discharge_decision')} docs={len(chain)} new={new_docs}")

        if phase in ("discharge", "confirm", "handoff", "review"):
            handoff = tr.get("handoff_items", [])
            print(f"\n  DISCHARGED! handoff {len(handoff)} items:")
            for h in handoff[:4]:
                print(f"      [{h.get('type','?')}] {h.get('content', '')[:120]}")
            doc_chain = chain
            result = tr
            break
        doc_chain = chain
        result = tr
    else:
        print(f"  #{i+1} Status: {type(tr).__name__}")

# final
final = get_state(pk)
if not final:
    final = result
chain = final.get("document_chain", [])
print(f"\nFinal: phase={final['phase']} docs={len(chain)} handoff={len(final.get('handoff_items',[]))} round={final.get('round_count')}")
print(f"  Full path: {' -> '.join(chain)}")
print(f"  Total checkpoints: {review_count}")

cleanup_patient_loop(pk)
