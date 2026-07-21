"""3患者人机协同全链路 — HTN/肺炎/肝硬化，AUTO_APPROVE=false"""
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

SEP = chr(9472) * 70
PATIENTS_TO_RUN = ["pat-htn-001", "pat-pneumonia-001", "pat-cirrhosis-001"]

for pk in PATIENTS_TO_RUN:
    p = PATIENTS[pk]
    disease = p["disease_id"]
    
    print(f"\n{'='*70}")
    print(f"  Patient: {p['name']} | {disease} | {p['description']}")
    print(f"{'='*70}")
    print(f"  Meds: {p['patient_history'].get('medications',[])}")
    print(f"  Labs: {[(l['name'], l['value'], l['unit']) for l in p['lab_results'][:4]]}")
    print(f"  VS trend: {len(p['vital_signs_sequence'])} rounds")
    
    loop = get_patient_loop(pk)
    state = loop.gen_input("new_admission")
    state["patient_id"] = pk
    for k in ["patient_data", "patient_history", "allergies", "lab_results"]:
        state[k] = p.get(k, state.get(k, []))
    state["disease_template"] = load_template(disease)
    
    # ---- First plan_turn ----
    result = asyncio.run(loop.plan_turn(state))
    
    checkpoint_count = 0
    doc_chain = []
    vital_rounds = 0
    
    # Handle initial checkpoint
    if isinstance(result, dict) and result.get("status") == "pending_review":
        checkpoint_count += 1
        payload = result.get("payload", {})
        print(f"\n  {SEP}")
        print(f"  Checkpoint #{checkpoint_count}: {payload.get('type','?')}")
        
        template_name = "?"
        try:
            tpl = state.get("disease_template", {})
            template_name = tpl.get("name") or tpl.get("disease_id", "?")
        except:
            pass
        print(f"  Template: {template_name}")
        print(f"\n  Doctor reviewing... approving")
        
        s = loop._current_state or state
        s["doctor_confirm_status"] = "approved"
        s.pop("pending_review", None)
        s.pop("interrupt_pending", None)
        set_state(pk, s)
        result = asyncio.run(loop.plan_turn(s))
    
    if isinstance(result, dict) and "phase" in result and "status" not in result:
        set_state(pk, result)
        doc_chain = result.get("document_chain", [])
        dc = result.get("discharge_decision")
        alerts = (result.get("clinical_alerts") or [])
        ddx = [(d.get("diagnosis","?")[:25], d.get("likelihood","?")) for d in (result.get("ddx_list") or [])[:4]]
        
        print(f"  Admission chain: {' -> '.join(doc_chain[:8])}...")
        print(f"  Phase: {result.get('phase')} | Risk: {result.get('risk_level')} | DC: {dc}")
        print(f"  DDx: {ddx}")
        if alerts:
            print(f"  Alerts: {alerts[:3]}")
        print(f"  DC criteria: {json.dumps(result.get('discharge_criteria_check',{}), ensure_ascii=False)[:150]}")
    
    # ---- Monitoring rounds ----
    vitals = list(p["vital_signs_sequence"])
    discharged = False
    
    for i, vs in enumerate(vitals[:8]):  # max 8 rounds
        current = get_state(pk) or result
        vss = list(current.get("vital_signs", []) or []) + [vs]
        update_state(pk, {"vital_signs": vss, "vital_signs_count": len(vss)})
        current = get_state(pk)
        tr = asyncio.run(loop.plan_turn(current))
        
        is_review = isinstance(tr, dict) and tr.get("status") == "pending_review"
        is_state = isinstance(tr, dict) and "phase" in tr and "status" not in tr
        
        if is_review:
            checkpoint_count += 1
            payload = tr.get("payload", {})
            rtype = payload.get("type", "?")
            
            print(f"\n  {SEP}")
            print(f"  Checkpoint #{checkpoint_count}: {rtype} (vital round {i+1})")
            
            if rtype == "med_confirm":
                adj = payload.get("medication_adjustments", []) or []
                print(f"  Adjustments ({payload.get('adjustment_count',0)}):")
                for a in (adj or [])[:3]:
                    print(f"    {json.dumps(a, ensure_ascii=False)[:120]}")
                print(f"  Vital trend: {json.dumps(payload.get('vital_trend',[])[:3], ensure_ascii=False)[:150]}")
                al = payload.get("abnormal_labs") or []
                if al: print(f"  Abnormal labs: {al[:3]}")
                print(f"\n  Doctor: approving medication adjustment")
                
                s = get_state(pk) or loop._current_state or current
                s["med_confirm_status"] = "approved"
                s.pop("pending_review", None)
                s.pop("interrupt_pending", None)
                set_state(pk, s)
                tr = asyncio.run(loop.plan_turn(s))
                
            elif rtype == "discharge_sign":
                ho = payload.get("handoff_count", 0)
                print(f"  DC: {payload.get('discharge_decision')} | Handoff items: {ho}")
                print(f"  Criteria: {json.dumps(payload.get('discharge_criteria_check',{}), ensure_ascii=False)[:150]}")
                print(f"\n  Doctor: signing discharge")
                
                s = get_state(pk) or loop._current_state or current
                s["discharge_sign_status"] = "signed"
                s.pop("pending_review", None)
                s.pop("interrupt_pending", None)
                set_state(pk, s)
                tr = asyncio.run(loop.plan_turn(s))
                
            elif rtype == "doctor_confirm":
                print(f"  Doctor: approving admission")
                s = get_state(pk) or loop._current_state or current
                s["doctor_confirm_status"] = "approved"
                s.pop("pending_review", None)
                s.pop("interrupt_pending", None)
                set_state(pk, s)
                tr = asyncio.run(loop.plan_turn(s))
        
        if is_state:
            set_state(pk, tr)
            phase = tr.get("phase", "")
            chain = tr.get("document_chain", [])
            new_docs = [d for d in chain if d not in doc_chain]
            g = vs.get("blood_glucose_fasting") or vs.get("systolic_mmhg", "?")
            vs_desc = f"VS#{i+1} val={g}" if g != "?" else f"VS#{i+1}"
            
            print(f"  {vs_desc} -> phase={phase} round={tr.get('round_count')} dc={tr.get('discharge_decision')} docs={len(chain)}")
            if new_docs:
                print(f"    NEW docs: {new_docs}")
                if "handoff_note" in new_docs:
                    for h in (tr.get("handoff_items") or [])[:2]:
                        print(f"      [{h.get('type','?')}] {h.get('content','')[:100]}")
            
            if phase in ("discharge", "confirm", "handoff", "review"):
                discharged = True
                result = tr
                doc_chain = chain
                break
            doc_chain = chain
            result = tr
        else:
            vital_rounds += 1
    
    # ---- Final ----
    final = get_state(pk) or result
    chain = final.get("document_chain", [])
    if discharged:
        print(f"\n  Discharged! phase={final['phase']} docs={len(chain)} handoff={len(final.get('handoff_items',[]))} rounds={final.get('round_count')}")
    else:
        print(f"\n  Still monitoring after {len(vitals)} rounds (max reached)")
    
    print(f"  Total checkpoints triggered: {checkpoint_count}")
    print(f"  Path: {' -> '.join(chain)}")
    
    cleanup_patient_loop(pk)
    print()
