"""糖尿病 王建国 — 逐节点全链路追踪（AUTO_APPROVE=true 快速走通过）"""
import os, sys, asyncio, json

os.environ["SKIP_BRIDGE"] = "true"
os.environ["DOCTOR_AUTO_APPROVE"] = "true"
os.environ["GRAPH_MODE"] = "classic"
os.environ["APP_ENV"] = "dev"
PROJ_SRC = os.path.join(os.path.dirname(__file__), "..", "services", "inpatient-ward", "src")
sys.path.insert(0, PROJ_SRC)

from zhenhu.inpatient.routes.patient_fixtures import PATIENTS
from zhenhu.inpatient.agent.loop import get_patient_loop, cleanup_patient_loop
from zhenhu.inpatient.agent.nodes import load_template
from zhenhu.inpatient.routes.state_store import set_state, get_state, update_state

pk = "pat-dm-001"
p = PATIENTS[pk]

def header(n):
    print(f"\n{'='*70}")
    print(f"  {n}")
    print(f"{'='*70}")

def show(title, data, limit=150):
    v = data
    if isinstance(v, dict):
        v = json.dumps(v, ensure_ascii=False)
    v = str(v)
    if len(v) > limit:
        v = v[:limit] + "..."
    print(f"  {title}: {v}")

# ============================================
# PATIENT INFO
# ============================================
header(f"Patient: {p['name']} | {p['disease_id']} | {p['description']}")
print(f"  Age: {p['patient_data']['age']} | BMI: {p['patient_data']['bmi']}")
print(f"  Comorbidities: {p['patient_history']['comorbidities']}")
print(f"  Meds: {p['patient_history']['medications']}")
print(f"  Hypoglycemia history: {p['patient_history'].get('hypoglycemia_history')}")
print(f"  Allergies: {p['allergies']}")
print(f"  Labs: {[(l['name'], l['value'], l['unit']) for l in p['lab_results']]}")
print(f"  VS sequence ({len(p['vital_signs_sequence'])}): glucose {p['vital_signs_sequence'][0]['blood_glucose_fasting']}->{p['vital_signs_sequence'][-1]['blood_glucose_fasting']} mmol/L")

# ============================================
# INIT STATE
# ============================================
header("Phase 1: Create Initial State (gen_input + fixture injection)")
loop = get_patient_loop(pk)
state = loop.gen_input("new_admission")
state["patient_id"] = pk
state["patient_data"] = p["patient_data"]
state["patient_history"] = p.get("patient_history", {})
state["allergies"] = p.get("allergies", [])
state["lab_results"] = p.get("lab_results", [])
state["disease_template"] = load_template(p["disease_id"])

t = state["disease_template"]
show("Template name", t.get("name"))
show("Discharge criteria", t.get("discharge_criteria", [])[:3])
show("Vital signs config", t.get("vital_signs", [])[:2])

# ============================================
# FIRST PLAN_TURN — ADMISSION FULL CHAIN
# ============================================
header("Phase 2: First plan_turn (Admission Full Chain)")
result = asyncio.run(loop.plan_turn(state))

if isinstance(result, dict) and result.get("status") == "pending_review":
    print("  [pending_review — AUTO_APPROVE should have prevented this]")
else:
    set_state(pk, result)
    chain = result.get("document_chain", [])
    
    for i, doc in enumerate(chain):
        node_num = i + 1
        marker = ""

        if doc == "intake_note":
            marker = "Admission registration"
        elif doc == "history_note":
            marker = f"History taking (CC+HPI+ROS+allergies+FH+SH)"
        elif doc == "pe_note":
            marker = f"Physical exam (Bates protocol)"
        elif doc == "ddx_note":
            marker = f"DDx: {[(d.get('diagnosis','?')[:20], d.get('likelihood','?')) for d in (result.get('ddx_list') or [])]}"
        elif doc == "medication_reconciliation":
            marker = "Medication reconciliation (rule-based + LLM)"
        elif doc == "risk_assessment":
            marker = f"Triage => risk_level={result.get('risk_level')}"
        elif doc == "doctor_confirm_auto":
            marker = "Checkpoint 1: Admission confirm (AUTO_APPROVED)"
        elif doc == "lab_review":
            marker = "Lab review (abnormal labs checked)"
        elif doc == "daily_round_note":
            marker = f"Daily round SOAP (round {result.get('round_count', '?')})"
        elif doc == "nursing_note":
            n_recs = len(result.get("nursing_records", []) or [])
            marker = f"Nursing plan ({n_recs} records)"
        elif doc == "discharge_signed":
            marker = "Checkpoint 3: Discharge signed"
        elif doc == "handoff_note":
            marker = f"Handoff generated ({len(result.get('handoff_items', []))} items)"
        elif doc == "review_note":
            marker = "Doctor review"
        elif doc == "confirm_note":
            marker = "Patient confirm"
        else:
            marker = str(result.get(doc.replace("_note", ""), {}))[:100]
        
        print(f"  [{node_num:2}] {doc:30s} | {marker}")

    show("Phase after admission", result.get("phase"))
    show("Risk level", result.get("risk_level"))
    show("DDx list", result.get("ddx_list", [])[:3])
    show("History data", f"CC='{(result.get('history_data',{}) or {}).get('chief_complaint','?')[:60]}' | HPI={(result.get('hpi_narrative') or 'None')[:80]}")
    show("PE data", f"PE={(result.get('pe_narrative') or 'None')[:80]} | systems={len((result.get('pe_data',{}) or {}).get('required_systems',[]))}")
    show("Clinical alerts", result.get("clinical_alerts", []))
    show("Discharge decision", result.get("discharge_decision"))
    show("Discharge criteria", result.get("discharge_criteria_check", {}))

doc_chain = chain

# ============================================
# MONITORING ROUNDS
# ============================================
header("Phase 3: Monitoring Rounds (vital sign push per round)")
vitals = list(p["vital_signs_sequence"])

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
        payload = tr.get("payload", {})
        rtype = payload.get("type", "?")
        print(f"\n  [{i+1}] VS glucose={vs['blood_glucose_fasting']} BP={vs['systolic_mmhg']}/{vs['diastolic_mmhg']}")
        print(f"      => CHECKPOINT: {rtype}")
        if rtype == "med_confirm":
            show("      Adjustments", payload.get("medication_adjustments", [])[:3])
    elif is_state:
        set_state(pk, tr)
        phase = tr.get("phase", "")
        chain = tr.get("document_chain", [])
        new_docs = [d for d in chain if d not in doc_chain]
        round_count = tr.get("round_count", 0)
        dc = tr.get("discharge_decision")
        alerts = tr.get("clinical_alerts", []) or []
        ddx = tr.get("ddx_list", []) or []
        g = vs.get("blood_glucose_fasting", "?")
        
        out = f"VS#{i+1}: glu={g} BP={vs['systolic_mmhg']}/{vs['diastolic_mmhg']}"
        out += f" | round={round_count} | phase={phase} | dc={dc}"
        if new_docs:
            out += f" | NEW={new_docs}"
        out += f" | docs={len(chain)}"
        out += f" | DDx={len(ddx)} | alerts={len(alerts)}"
        print(f"  {out}")
        
        # Show monitoring node results
        if tr.get("latest_round"):
            soap = tr["latest_round"]
            show("  SOAP", f"stability={soap.get('stability')} | response={soap.get('response_to_treatment','?')[:80]} | findings={str(soap.get('key_findings',''))[:80]}")
        
        if new_docs:
            for nd in new_docs:
                if nd == "discharge_signed":
                    show("  => Discharge checkpoint passed", "AUTO_APPROVED")
                elif nd == "handoff_note":
                    items = tr.get("handoff_items", [])
                    for h in items[:3]:
                        show(f"    Handoff [{h.get('type','?')}]", h.get("content", "")[:120])
                elif nd == "medication_adjust":
                    show("  => Medication adjusted", tr.get("medication_adjustments", [])[-1:] if tr.get("medication_adjustments") else "none")
        
        if phase in ("discharge", "confirm", "handoff", "review"):
            doc_chain = chain
            result = tr
            break
        doc_chain = chain
        result = tr

# ============================================
# FINAL
# ============================================
header("Phase 4: Discharge Summary")
final = get_state(pk) or result
chain = final.get("document_chain", [])
handoff = final.get("handoff_items", []) or []

print(f"  Phase: {final.get('phase')} | Risk: {final.get('risk_level')} | Discharge: {final.get('discharge_decision')}")
print(f"  Round: {final.get('round_count')} | Docs: {len(chain)} | Handoff: {len(handoff)}")
print(f"\n  Complete node path:")
nodes_shown = []
for i, d in enumerate(chain):
    dedup = "" if d not in nodes_shown else " (duplicate)"
    print(f"    {i+1:2}. {d}{dedup}")
    nodes_shown.append(d)

print(f"\n  Discharge DDx:")
for d in (final.get("ddx_list") or [])[:5]:
    print(f"    - {d.get('diagnosis','?')} [{d.get('likelihood','?')}]")

print(f"\n  Handoff items:")
for h in handoff[:5]:
    print(f"    - [{h.get('type','?')}] {h.get('content','')[:150]}")

print(f"\n  Discharge criteria: {final.get('discharge_criteria_check')}")

cleanup_patient_loop(pk)
