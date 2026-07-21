"""全节点覆盖 + 全路由验证 — 14 患者全链路压测最"""

import os, sys, asyncio, json
os.environ['SKIP_BRIDGE'] = 'true'
os.environ['DOCTOR_AUTO_APPROVE'] = 'true'
os.environ['GRAPH_MODE'] = 'classic'
os.environ['APP_ENV'] = 'dev'
sys.path.insert(0, 'services/inpatient-ward/src')

from zhenhu.inpatient.routes.patient_fixtures import PATIENTS
from zhenhu.inpatient.agent.loop import get_patient_loop, cleanup_patient_loop
from zhenhu.inpatient.agent.nodes import load_template
from zhenhu.inpatient.routes.state_store import set_state, get_state, update_state

EXPECTED_NODES = {
    'intake_note','history_note','pe_note','ddx_note',
    'medication_reconciliation','risk_assessment','doctor_confirm_auto',
    'padua_scored','vte_check','news2_alert','qsofa_alert',
    'lab_review','daily_round_note','nursing_note',
    'discharge_signed','handoff_note','review_note','confirm_note'
}
SCORE_NODES = {'padua_scored','vte_check','news2_alert','qsofa_alert','mdt_triggered','stroke_at_check'}

results = []
for pk in PATIENTS:
    p = PATIENTS[pk]
    disease = p['disease_id']
    loop = get_patient_loop(pk)
    state = loop.gen_input('new_admission')
    state['patient_id'] = pk
    for k in ['patient_data','patient_history','allergies','lab_results']:
        state[k] = p.get(k, [])
    state['disease_template'] = load_template(disease)

    r = asyncio.run(loop.plan_turn(state))
    if isinstance(r, dict) and 'phase' in r:
        set_state(pk, r)
        chain = r.get('document_chain', [])
        alerts = r.get('clinical_alerts', []) or []
        score_triggered = [n for n in SCORE_NODES if n in chain]
        vte_alerts = [a for a in alerts if 'VTE' in str(a)]
        news2 = r.get('news2_score')
        padua = r.get('padua_score')
        qsofa = r.get('qsofa_score')
    else:
        chain = []

    # Push vital signs sequence
    vitals = list(p['vital_signs_sequence'])
    discharged = False
    for i, vs in enumerate(vitals[:10]):
        current = get_state(pk) or r
        vss = list(current.get('vital_signs', []) or []) + [vs]
        update_state(pk, {'vital_signs': vss, 'vital_signs_count': len(vss)})
        tr = asyncio.run(loop.plan_turn(get_state(pk)))
        if isinstance(tr, dict) and 'phase' in tr and 'status' not in tr:
            set_state(pk, tr)
            phase = tr.get('phase', '')
            chain2 = tr.get('document_chain', [])
            alerts2 = tr.get('clinical_alerts', []) or []
            new_score = [n for n in SCORE_NODES if n in chain2 and n not in chain]
            if phase in ('discharge','confirm','handoff','review'):
                discharged = True
                chain = chain2
                break
            chain = chain2

    final = get_state(pk) or r
    chain = final.get('document_chain', [])
    missing = [n for n in EXPECTED_NODES if n not in chain]
    dupes = [n for n in chain if chain.count(n) > 1]
    score_hits = [n for n in SCORE_NODES if n in chain]
    alerts = final.get('clinical_alerts', []) or []

    results.append({
        'pk': pk, 'disease': disease,
        'discharged': discharged,
        'chain_len': len(chain),
        'missing': missing,
        'dupes': dupes,
        'score_nodes': score_hits,
        'alerts': len(alerts),
        'vte_alerts': [a for a in alerts if 'VTE' in str(a)][:2],
        'news2_stroke': [a for a in alerts if 'NEWS2' in str(a) or 'STK' in str(a)][:2],
    })
    cleanup_patient_loop(pk)

print(f"{'Patient':25s} {'Disease':15s} {'Disch':6s} {'Chain':6s} {'Alerts':6s} {'Missing':30s} {'Dupes':20s} {'ScoreNodes'}")
print("-" * 130)
for r in results:
    missing_str = ','.join(r['missing'][:3]) if r['missing'] else '-'
    dupes_str = ','.join(r['dupes'][:3]) if r['dupes'] else '-'
    score_str = '+'.join([n.split('_')[0] for n in r['score_nodes']])
    print(f"{r['pk']:25s} {r['disease']:15s} {str(r['discharged']):6s} {r['chain_len']:<6d} {r['alerts']:<6d} {missing_str:30s} {dupes_str:20s} {score_str}")

# Summary
all_discharged = all(r['discharged'] for r in results)
any_missing = [r for r in results if r['missing']]
any_dupes = [r for r in results if r['dupes']]
all_padua = all('padua_scored' in r['score_nodes'] for r in results)
all_vte = all('vte_check' in r['score_nodes'] for r in results)

print(f"\n=== SUMMARY ===")
print(f"Discharged: {sum(1 for r in results if r['discharged'])}/{len(results)}")
print(f"Padua scored: {all_padua}")
print(f"VTE checked: {all_vte}")
print(f"Any missing: {len(any_missing)} patients ({[r['pk'] for r in any_missing]})")
print(f"Any dupes: {len(any_dupes)} patients ({[r['pk'] for r in any_dupes]})")
print(f"RESULT: {'ALL CLEAN' if all_discharged and not any_missing and not any_dupes else 'HAS ISSUES'}")
