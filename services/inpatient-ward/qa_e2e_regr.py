import asyncio, os, sys
os.environ['SKIP_BRIDGE'] = 'true'; os.environ['DOCTOR_AUTO_APPROVE'] = 'true'
os.environ['GRAPH_MODE'] = 'classic'; os.environ['APP_ENV'] = 'dev'
sys.path.insert(0, 'src')
from zhenhu.inpatient.routes.patient_fixtures import PATIENTS
from zhenhu.inpatient.agent.loop import get_patient_loop, cleanup_patient_loop
from zhenhu.inpatient.agent.nodes import load_template
from zhenhu.inpatient.routes.state_store import set_state, get_state, update_state

async def quick_check(key):
    p = PATIENTS[key]
    loop = get_patient_loop(key)
    disease_id = p['disease_id']
    state = loop.gen_input('new_admission')
    state['patient_id'] = key
    state['patient_data'] = p['patient_data']
    state['patient_history'] = p.get('patient_history', {})
    state['allergies'] = p.get('allergies', [])
    state['lab_results'] = p.get('lab_results', [])
    state['disease_template'] = load_template(disease_id)
    result = await loop.plan_turn(state)
    set_state(key, result)
    vitals = list(p['vital_signs_sequence'])
    for i, vs in enumerate(vitals):
        current = get_state(key)
        if not current: current = result
        vss = list(current.get('vital_signs', []) or []) + [vs]
        update_state(key, {'vital_signs': vss, 'vital_signs_count': len(vss)})
        current = get_state(key)
        turn_result = await loop.plan_turn(current)
        if isinstance(turn_result, dict) and 'phase' in turn_result and 'status' not in turn_result:
            set_state(key, turn_result)
            result = turn_result
            phase = turn_result.get('phase', '')
            handoff = turn_result.get('handoff_items', [])
            if phase in ('discharge', 'confirm', 'handoff', 'review') or handoff:
                break
    final = get_state(key) or result
    doc_chain = final.get('document_chain', [])
    alerts = final.get('clinical_alerts', [])
    phase = final.get('phase', '')
    print(f'{key} ({p["name"]}) disease={disease_id}')
    print(f'  Phase: {phase}')
    print(f'  vte_check: {"vte_check" in doc_chain}  stroke_at_check: {"stroke_at_check" in doc_chain}')
    vte_alerts = [a for a in alerts if 'VTE' in a]
    stk_alerts = [a for a in alerts if 'STK' in a]
    print(f'  VTE alerts: {vte_alerts}')
    print(f'  STK alerts: {stk_alerts}')
    cleanup_patient_loop(key)
    return {'vte_check': 'vte_check' in doc_chain, 'stroke_at_check': 'stroke_at_check' in doc_chain}

for key in ['pat-stroke-001', 'pat-gi_bleeding-001']:
    print('---')
    asyncio.run(quick_check(key))
