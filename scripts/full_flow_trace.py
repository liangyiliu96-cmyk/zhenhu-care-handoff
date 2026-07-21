"""全链路追踪脚本：高血压患者张建国 入院→监测→出院 详细过程。

运行:
    cd services/inpatient-ward
    SKIP_BRIDGE=true DOCTOR_AUTO_APPROVE=true GRAPH_MODE=classic python ../../scripts/full_flow_trace.py
"""

import os
import sys

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

SEP = "=" * 80
SUB = "-" * 60

def sprint(title, content=None):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)
    if content:
        print(content)

def pstate(state, keys=None):
    """打印 state 关键字段"""
    if keys is None:
        keys = [
            "phase", "document_chain", "risk_level", "discharge_decision",
            "clinical_alerts", "ddx_list", "handoff_items", "medication_adjustments",
            "hpi_narrative", "pe_narrative", "chief_complaint", "allergies",
            "nursing_records",
        ]
    for k in keys:
        v = state.get(k)
        if v and isinstance(v, (list, str)):
            if isinstance(v, str) and len(v) > 200:
                v = v[:200] + "..."
            elif isinstance(v, list) and len(v) > 5:
                v = v[:5]
            print(f"  {k}: {v}")


# ============================================================
# 第 1 步：患者信息
# ============================================================
patient_key = "pat-htn-001"
p = PATIENTS[patient_key]

sprint(f"📋 患者: {p['name']} ({patient_key})", f"""\
  诊断: {p['description']}
  病种: {p['disease_id']}
  主诉: {p['patient_data']['chief_complaint']}
  过敏史: {p['allergies']}
  合并症: {p['patient_history']['comorbidities']}
  入院用药: {p['patient_history']['medications']}
  体征序列: {len(p['vital_signs_sequence'])} 次
  检验: {len(p['lab_results'])} 项
  吸烟: {p['patient_history']['smoking']}
  CVD家族史: {p['patient_history']['family_history_cvd']}
""")


# ============================================================
# 第 2 步：创建入院 state
# ============================================================
sprint("🔄 第 2 步：创建入院初始状态 (gen_input + fixture 注入)")

loop = get_patient_loop(patient_key)
disease_id = p["disease_id"]
state = loop.gen_input("new_admission")
state["patient_id"] = patient_key
state["patient_data"] = p["patient_data"]
state["patient_history"] = p.get("patient_history", {})
state["allergies"] = p.get("allergies", [])
state["lab_results"] = p.get("lab_results", [])
state["disease_template"] = load_template(disease_id)

print(f"  initial phase: {state['phase']}")
print(f"  template: {state['disease_template'].get('name', disease_id)}")
print(f"  round_count: {state['round_count']}")
print(f"  initial lab_results: {state['lab_results']}")


# ============================================================
# 第 3 步：首次 plan_turn — 入院→分诊→会诊→查房→护理→出院判定
# ============================================================
sprint("🔄 第 3 步：首次 plan_turn（入院全链路）")

import asyncio
result = asyncio.run(loop.plan_turn(state))
set_state(patient_key, result)

sprint("📊 首次 plan_turn 结果", "")
print(f"  phase: {result.get('phase')}")
print(f"  document_chain ({len(result.get('document_chain', []))} 文档):")
for doc in result.get("document_chain", []):
    print(f"    ✓ {doc}")
print(f"  risk_level: {result.get('risk_level')}")
print(f"  history_data keys: {list(result.get('history_data', {}).keys()) if result.get('history_data') else 'None'}")
print(f"  pe_data keys: {list(result.get('pe_data', {}).keys()) if result.get('pe_data') else 'None'}")
print(f"  ddx_list ({len(result.get('ddx_list', []) or [])} 条):")
for d in (result.get('ddx_list') or [])[:5]:
    print(f"    • {d.get('diagnosis', '?')} (ICD-10: {d.get('icd10', '?')}, likelihood: {d.get('likelihood', '?')})")
print(f"  hpi_narrative: {str(result.get('hpi_narrative', ''))[:200]}")
print(f"  pe_narrative: {str(result.get('pe_narrative', ''))[:200]}")
print(f"  clinical_alerts ({len(result.get('clinical_alerts', []) or [])}):")
for a in (result.get('clinical_alerts') or [])[:5]:
    print(f"    ⚠ {a}")
print(f"  medication_adjustments: {len(result.get('medication_adjustments', []) or [])} 条")
print(f"  nursing_records: {len(result.get('nursing_records', []) or [])} 条")
print(f"  discharge_decision: {result.get('discharge_decision')}")


# ============================================================
# 第 4 步：多轮体征监测
# ============================================================
sprint("🔄 第 4 步：逐次上报体征，驱动多轮监测")

vitals = list(p["vital_signs_sequence"])
for i, vs in enumerate(vitals):
    current = get_state(patient_key)
    if not current:
        current = result

    vss = list(current.get("vital_signs", []) or []) + [vs]
    update_state(patient_key, {"vital_signs": vss, "vital_signs_count": len(vss)})
    current = get_state(patient_key)

    turn_result = asyncio.run(loop.plan_turn(current))

    is_review = isinstance(turn_result, dict) and turn_result.get("status") == "pending_review"
    is_state = isinstance(turn_result, dict) and "phase" in turn_result and "status" not in turn_result

    print(f"\n{SUB}")
    print(f"  体征 #{i+1}/{len(vitals)}: BP={vs['systolic_mmhg']}/{vs['diastolic_mmhg']} HR={vs['heart_rate']} SpO2={vs['spo2']} Temp={vs['temperature']}")

    if is_state:
        set_state(patient_key, turn_result)
        doc_chain = turn_result.get("document_chain", [])
        phase = turn_result.get("phase", "")
        handoff = turn_result.get("handoff_items", [])

        # 只打印本轮新增的文档
        prev_chain = result.get("document_chain", [])
        new_docs = [d for d in doc_chain if d not in prev_chain]
        if new_docs:
            print(f"  新增文档: {new_docs}")
        print(f"  phase: {phase}")
        print(f"  discharge_decision: {turn_result.get('discharge_decision')}")
        print(f"  risk_level: {turn_result.get('risk_level')}")
        print(f"  clinical_alerts count: {len(turn_result.get('clinical_alerts', []) or [])}")
        print(f"  ddx_list count: {len(turn_result.get('ddx_list', []) or [])}")
        print(f"  document_chain length: {len(doc_chain)}")
        print(f"  round_count: {turn_result.get('round_count', 0)}")
        print(f"  SOAP 最新评估: {str(turn_result.get('latest_round', {}).get('assessment', ''))[:150]}")

        result = turn_result

        # 出院检查
        if phase in ("discharge", "confirm", "handoff", "review"):
            print(f"\n  🎉 进入出院阶段！phase={phase}")
            if handoff:
                print(f"  handoff_items ({len(handoff)} 条):")
                for h in handoff[:5]:
                    print(f"    • [{h.get('type', '?')}] {str(h.get('content', ''))[:120]}")
            break
    elif is_review:
        review_type = turn_result.get("payload", {}).get("type", "")
        print(f"  ⏸ 卡点触发: {review_type} — AUTO_APPROVE 自动通过")
        state_current = get_state(patient_key)
        if review_type == "doctor_confirm":
            state_current["doctor_confirm_status"] = "approved"
        elif review_type == "med_confirm":
            state_current["med_confirm_status"] = "approved"
        elif review_type == "discharge_sign":
            state_current["discharge_sign_status"] = "signed"
        turn_result2 = asyncio.run(loop.plan_turn(state_current))
        if isinstance(turn_result2, dict) and "phase" in turn_result2:
            set_state(patient_key, turn_result2)
            result = turn_result2
            print(f"  → graph resume, phase: {turn_result2.get('phase')}")
    else:
        print(f"  返回类型: {type(turn_result).__name__}")
        print(f"  内容: {str(turn_result)[:200]}")


# ============================================================
# 第 5 步：出院总结
# ============================================================
sprint("🎉 第 5 步：最终状态 — 出院总结")

final = get_state(patient_key)
if not final:
    final = result

phase = final.get("phase", "unknown")
doc_chain = final.get("document_chain", [])
handoff = final.get("handoff_items", [])
ddx = final.get("ddx_list", []) or []

print(f"\n  患者: {p['name']}")
print(f"  诊断: {p['disease_id']}")
print(f"  最终阶段: {phase}")
print(f"  出入院决定: {final.get('discharge_decision')}")

print(f"\n  📄 完整文档链 ({len(doc_chain)} 项):")
for i, doc in enumerate(doc_chain):
    print(f"    {i+1:2}. {doc}")

print(f"\n  🏥 出院诊断 ({len(ddx)} 条):")
for d in ddx:
    print(f"    • {d.get('diagnosis', '?')} (ICD-10: {d.get('icd10', '?')}, likelihood: {d.get('likelihood', '?')})")

print(f"\n  📋 交接事项 ({len(handoff)} 条):")
for h in handoff:
    print(f"    • [{h.get('type', '?')}] {h.get('content', '')[:150]}")

print(f"\n  ⚠ 临床告警 ({len(final.get('clinical_alerts', []) or [])} 条):")
for a in (final.get('clinical_alerts') or [])[:10]:
    print(f"    • {a}")

print(f"\n  💊 用药方案 ({len(final.get('medication_adjustments', []) or [])} 条):")
for m in (final.get('medication_adjustments') or [])[:5]:
    print(f"    • {m}")

print(f"\n  📊 体征序列 ({len(final.get('vital_signs', []) or [])} 次):")
for vs in (final.get('vital_signs') or [])[-5:]:
    print(f"    • BP={vs.get('systolic_mmhg')}/{vs.get('diastolic_mmhg')} HR={vs.get('heart_rate')} SpO2={vs.get('spo2')}")

print(f"\n  📝 完整 HPI: {str(final.get('hpi_narrative', ''))[:300]}")
print(f"  📝 完整 PE: {str(final.get('pe_narrative', ''))[:300]}")
print(f"  📝 主诉: {final.get('history_data', {}).get('chief_complaint', 'N/A')}")

print(f"\n  🏥 出院标准检查: {final.get('discharge_criteria_check')}")

# 清理
cleanup_patient_loop(patient_key)

sprint("✅ 全链路追踪完成")
print(f"  病种: {disease_id}")
print(f"  节点路径: {' → '.join(doc_chain)}")
print(f"  文档数: {len(doc_chain)}")
print(f"  交接事项: {len(handoff)}")
print(f"  体征轮次: {len(vitals)}")
print(f"  最终阶段: {phase}")
