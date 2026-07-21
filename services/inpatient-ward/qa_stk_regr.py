import asyncio, os, sys
os.environ['SKIP_BRIDGE'] = 'true'
sys.path.insert(0, 'src')
from zhenhu.inpatient.agent.nodes_scoring import node_stroke_antithrombotic

async def test():
    results = []
    
    # TEST1: stroke + missing -> STK-2 alert (KEY: no phase field!)
    s1 = {'patient_id': 's1', 'document_chain': [], 
          'disease_template': {'name': 'stroke'}, 'medication_adjustments': [],
          'handoff_items': [], 'ddx_list': [], 'clinical_alerts': []}
    r1 = await node_stroke_antithrombotic(s1)
    ok1 = 'stroke_at_check' in r1.get('document_chain',[])
    has1 = any('STK-2' in a for a in (r1.get('clinical_alerts') or []))
    print(f"TEST1 stroke noAT: stroke_at_check={ok1} STK2_alert={has1} -> {'PASS' if ok1 and has1 else 'FAIL'}")

    # TEST2: stroke + antithrombotic
    s2 = {'patient_id': 's2', 'document_chain': [], 
          'disease_template': {'name': 'ischemic stroke'}, 'medication_adjustments': [{'drug': 'aspirin'}],
          'handoff_items': [], 'ddx_list': [], 'clinical_alerts': []}
    r2 = await node_stroke_antithrombotic(s2)
    ok2 = 'stroke_at_check' in r2.get('document_chain',[])
    has2 = any('STK-2' in a for a in (r2.get('clinical_alerts') or []))
    print(f"TEST2 stroke+AT: stroke_at_check={ok2} STK2_alert={has2} -> {'PASS' if ok2 and not has2 else 'FAIL'}")

    # TEST3: non-stroke silent
    s3 = {'patient_id': 's3', 'document_chain': [], 
          'disease_template': {'name': 'hypertension'}, 'medication_adjustments': [],
          'handoff_items': [], 'ddx_list': [], 'clinical_alerts': []}
    r3 = await node_stroke_antithrombotic(s3)
    ok3 = 'stroke_at_check' in r3.get('document_chain',[])
    print(f"TEST3 non-stroke: stroke_at_check={ok3} -> {'PASS' if ok3 else 'FAIL'}")

    # TEST4: idempotent
    s4 = {'patient_id': 's4', 'document_chain': ['stroke_at_check']}
    r4 = await node_stroke_antithrombotic(s4)
    print(f"TEST4 idempotent: {r4} -> {'PASS' if r4 == {} else 'FAIL'}")

    # TEST5: TIA (lowercase fix)
    s5 = {'patient_id': 's5', 'document_chain': [], 
          'disease_template': {'name': 'TIA'}, 'medication_adjustments': [],
          'handoff_items': [], 'ddx_list': [], 'clinical_alerts': []}
    r5 = await node_stroke_antithrombotic(s5)
    ok5 = 'stroke_at_check' in r5.get('document_chain',[])
    has5 = any('STK-2' in a for a in (r5.get('clinical_alerts') or []))
    print(f"TEST5 TIA: stroke_at_check={ok5} STK2_alert={has5} -> {'PASS' if ok5 and has5 else 'FAIL'}")

    # TEST6: DDx stroke
    s6 = {'patient_id': 's6', 'document_chain': [], 
          'disease_template': {'name': 'hypertension'}, 'medication_adjustments': [{'drug': 'clopidogrel'}],
          'handoff_items': [], 'ddx_list': [{'diagnosis': 'ischemic stroke'}], 'clinical_alerts': []}
    r6 = await node_stroke_antithrombotic(s6)
    ok6 = 'stroke_at_check' in r6.get('document_chain',[])
    print(f"TEST6 DDx stroke: stroke_at_check={ok6} -> {'PASS' if ok6 else 'FAIL'}")

    # TEST7: handoff AT
    s7 = {'patient_id': 's7', 'document_chain': [], 
          'disease_template': {'name': '脑梗'}, 'medication_adjustments': [],
          'handoff_items': [{'content': '出院带药: 阿司匹林 100mg qd'}], 'ddx_list': [], 'clinical_alerts': []}
    r7 = await node_stroke_antithrombotic(s7)
    ok7 = 'stroke_at_check' in r7.get('document_chain',[])
    has7 = any('STK-2' in a for a in (r7.get('clinical_alerts') or []))
    print(f"TEST7 handoff AT: stroke_at_check={ok7} STK2_alert={has7} -> {'PASS' if ok7 and not has7 else 'FAIL'}")

asyncio.run(test())
