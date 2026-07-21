"""QA 全链路测试: 14 个 fixture 患者 入院→出院 端到端验证。

运行方式:
    SKIP_BRIDGE=true DOCTOR_AUTO_APPROVE=true GRAPH_MODE=classic python -m pytest tests/test_full_clinical_flow.py -q -s
"""

import asyncio
import os
import sys
import traceback
from pathlib import Path

# 环境变量（必须在任何导入前设置）
os.environ["SKIP_BRIDGE"] = "true"
os.environ["DOCTOR_AUTO_APPROVE"] = "true"
os.environ["GRAPH_MODE"] = "classic"
os.environ["APP_ENV"] = "dev"

# 确保项目路径在 sys.path 中
PROJ_SRC = Path(__file__).resolve().parent.parent / "src"
if str(PROJ_SRC) not in sys.path:
    sys.path.insert(0, str(PROJ_SRC))

from zhenhu.inpatient.routes.patient_fixtures import PATIENTS
from zhenhu.inpatient.agent.loop import get_patient_loop, cleanup_patient_loop
from zhenhu.inpatient.agent.nodes import load_template
from zhenhu.inpatient.routes.state_store import set_state, get_state, update_state

REQUIRED_DOCS = [
    "intake_note",
    "history_note",
    "pe_note",
    "ddx_note",
    "med_rec_note",
    "risk_assessment",
    "doctor_confirm_auto",
    "daily_round_note",
    "nursing_note",
    "lab_review",        # 注意: 实际文档链中名为 "lab_review" 非 "lab_review_note"
    "discharge_signed",
    "handoff_note",
    "doctor_review_note",
]

ACCEPTABLE_PHASES = ("discharge", "confirm", "handoff", "review")


async def _run_full_flow_for_patient(patient_key: str) -> dict:
    """为单患者跑完入院→监测→出院 全链路。"""
    p = PATIENTS[patient_key]
    loop = get_patient_loop(patient_key)
    disease_id = p["disease_id"]

    # 1. 创建入院 state（注入 fixture 数据）
    state = loop.gen_input("new_admission")
    state["patient_id"] = patient_key
    state["patient_data"] = p["patient_data"]
    state["patient_history"] = p.get("patient_history", {})
    state["allergies"] = p.get("allergies", [])
    state["lab_results"] = p.get("lab_results", [])
    state["disease_template"] = load_template(disease_id)

    # 2. 入院 → ... → monitoring（首次完整链路）
    result = await loop.plan_turn(state)
    set_state(patient_key, result)

    # 3. 逐步上报体征，驱动出院决策
    vitals = list(p["vital_signs_sequence"])
    for i, vs in enumerate(vitals):
        current = get_state(patient_key)
        if not current:
            current = result
        vss = list(current.get("vital_signs", []) or []) + [vs]
        update_state(patient_key, {"vital_signs": vss, "vital_signs_count": len(vss)})
        current = get_state(patient_key)

        turn_result = await loop.plan_turn(current)

        # plan_turn 可能返回完整 state 或 {"status": "pending_review", ...}
        is_review = isinstance(turn_result, dict) and turn_result.get("status") == "pending_review"
        is_state = isinstance(turn_result, dict) and "phase" in turn_result and "status" not in turn_result

        if is_review:
            # 卡点返回 → 手动批准（DOCTOR_AUTO_APPROVE 下通常不会走这里）
            review_type = turn_result.get("payload", {}).get("type", "")
            state_current = get_state(patient_key)
            if review_type == "doctor_confirm":
                state_current["doctor_confirm_status"] = "approved"
            elif review_type == "med_confirm":
                state_current["med_confirm_status"] = "approved"
            elif review_type == "discharge_sign":
                state_current["discharge_sign_status"] = "signed"
            turn_result = await loop.plan_turn(state_current)
            is_state = isinstance(turn_result, dict) and "phase" in turn_result

        if is_state:
            set_state(patient_key, turn_result)
            phase = turn_result.get("phase", "")
            handoff = turn_result.get("handoff_items", [])
            if phase in ACCEPTABLE_PHASES or (handoff and len(handoff) > 0):
                result = turn_result
                break
        else:
            # plan_turn 可能返回空或异常结果
            pass

        result = turn_result if is_state else current

    # 4. 提取验证指标
    final = get_state(patient_key)
    if not final or not isinstance(final, dict):
        final = result
    doc_chain = final.get("document_chain", []) if isinstance(final, dict) else []
    handoff = final.get("handoff_items", []) if isinstance(final, dict) else []
    phase = final.get("phase", "") if isinstance(final, dict) else ""

    return {
        "patient": patient_key,
        "name": p["name"],
        "disease": disease_id,
        "phase": phase,
        "doc_chain": doc_chain,
        "handoff_count": len(handoff) if handoff else 0,
        "history_data": bool(final.get("history_data")) if isinstance(final, dict) else False,
        "pe_data": bool(final.get("pe_data")) if isinstance(final, dict) else False,
        "ddx_list": bool(final.get("ddx_list")) if isinstance(final, dict) else False,
        "nursing_records": bool(final.get("nursing_records")) if isinstance(final, dict) else False,
        # 扩展指标
        "doc_count": len(doc_chain),
        "intake_note": "intake_note" in doc_chain,
        "risk_assessment": "risk_assessment" in doc_chain,
        "daily_round_note": "daily_round_note" in doc_chain,
        "history_note": "history_note" in doc_chain,
        "pe_note": "pe_note" in doc_chain,
        "ddx_note": "ddx_note" in doc_chain,
        "nursing_note": "nursing_note" in doc_chain,
        "handoff_note": "handoff_note" in doc_chain,
        "discharge_signed": "discharge_signed" in doc_chain,
        "allergy_status": final.get("allergy_status") if isinstance(final, dict) else None,
        "risk_level": final.get("risk_level") if isinstance(final, dict) else None,
        "discharge_decision": final.get("discharge_decision") if isinstance(final, dict) else None,
    }


async def main():
    results = []
    errors = []

    print("=" * 100)
    print("QA 全链路测试: 14 fixture 患者 入院→出院")
    print(f"  SKIP_BRIDGE=true  DOCTOR_AUTO_APPROVE=true  GRAPH_MODE=classic")
    print("=" * 100)

    for key in PATIENTS:
        p_name = PATIENTS[key]["name"]
        disease = PATIENTS[key]["disease_id"]
        print(f"\n--- [{disease}] {key}: {p_name} ---")
        try:
            r = await _run_full_flow_for_patient(key)
            results.append(r)
            print(f"  Phase      : {r['phase']:12s}")
            print(f"  Documents  : {r['doc_count']:2d}  ({', '.join(r['doc_chain'])})")
            print(f"  Handoff    : {r['handoff_count']}")
            print(f"  History    : {'OK' if r['history_data'] else '--'}  "
                  f"PE: {'OK' if r['pe_data'] else '--'}  "
                  f"DDx: {'OK' if r['ddx_list'] else '--'}  "
                  f"Nursing: {'OK' if r['nursing_records'] else '--'}")
        except Exception as e:
            print(f"  ERROR: {e}")
            traceback.print_exc()
            errors.append({"patient": key, "disease": disease, "error": str(e), "traceback": traceback.format_exc()})
            results.append({
                "patient": key, "name": p_name, "disease": disease,
                "phase": "ERROR", "doc_chain": [], "handoff_count": 0,
                "history_data": False, "pe_data": False, "ddx_list": False, "nursing_records": False,
            })

        # 清理患者实例
        cleanup_patient_loop(key)

    # ========================================================================
    # 汇总报告
    # ========================================================================
    print("\n" + "=" * 100)
    print("QA 测试报告汇总")
    print("=" * 100)

    total = len(PATIENTS)
    passed = sum(1 for r in results if r["phase"] in ACCEPTABLE_PHASES)
    errored = len(errors)

    print(f"\n[通过率] {passed}/{total} 患者到达 discharge/confirm/handoff/review ({100*passed//total}%)")

    if errored:
        print(f"\n[异常] {errored} 患者出现错误:")
        for e in errors:
            print(f"  - {e['disease']} ({e['patient']}): {e['error']}")

    # 文档链覆盖率
    print(f"\n[文档链覆盖率]")
    for doc_name in ["intake_note", "history_note", "pe_note", "ddx_note",
                      "medication_reconciliation", "risk_assessment", "doctor_confirm_auto",
                      "daily_round_note", "nursing_note", "lab_review", "discharge_signed", "handoff_note"]:
        count = sum(1 for r in results if doc_name in r["doc_chain"])
        pct = f"{100*count//total}%" if total > 0 else "0%"
        bar = "█" * (count * 4 // total) if total > 0 else ""
        print(f"  {doc_name:25s} {count:2d}/{total} ({pct:3s}) {bar}")

    # 各维度产出
    print(f"\n[临床数据维度产出]")
    dims = {
        "history_data": "病史采集数据",
        "pe_data": "体格检查数据",
        "ddx_list": "鉴别诊断列表",
        "nursing_records": "护理记录",
    }
    for key, label in dims.items():
        count = sum(1 for r in results if r.get(key))
        pct = f"{100*count//total}%" if total > 0 else "0%"
        print(f"  {label:15s} {count:2d}/{total} ({pct:3s})")

    # 各患者详情表
    print(f"\n[患者详情]")
    print(f"  {'患者':20s} {'病种':18s} {'Phase':12s} {'Docs':>4s} {'H/O':>3s} {'Hist':>5s} {'PE':>3s} {'DDx':>4s} {'Nur':>4s} {'PASS':>5s}")
    print(f"  {'-'*20} {'-'*18} {'-'*12} {'-'*4} {'-'*3} {'-'*5} {'-'*3} {'-'*4} {'-'*4} {'-'*5}")
    for r in results:
        pass_mark = "YES" if r["phase"] in ACCEPTABLE_PHASES else ("ERR" if r["phase"] == "ERROR" else "no")
        print(f"  {r['name']:20s} {r['disease']:18s} {r['phase']:12s} {r['doc_count']:4d} "
              f"{r['handoff_count']:3d} {'OK' if r['history_data'] else '--':5s} "
              f"{'OK' if r['pe_data'] else '--':3s} {'OK' if r['ddx_list'] else '--':4s} "
              f"{'OK' if r['nursing_records'] else '--':4s} {pass_mark:5s}")

    # 建议
    print(f"\n[QA 建议]")
    if passed < total:
        stuck = [r for r in results if r["phase"] not in ACCEPTABLE_PHASES and r["phase"] != "ERROR"]
        if stuck:
            print(f"  - {len(stuck)} 名患者未到达出院阶段，相位停留于 monitoring，需检查 discharge_criteria 阈值。")
            for r in stuck:
                print(f"    · {r['disease']}: phase={r['phase']}, discharge_decision={r.get('discharge_decision')}")
        if errored:
            print(f"  - {errored} 名患者出现异常崩溃，需排查节点内未处理的 None/TypeError。")
    else:
        print(f"  - 所有 {total} 名患者均到达出院/确认阶段，全链路通过。")

    return passed == total and errored == 0


# ============================================================================
# Pytest 入口
# ============================================================================
def test_all_14_patients(isolated_state_store):
    """pytest 测试: 14 患者全链路。"""
    ok = asyncio.run(main())
    assert ok, f"全链路测试未完全通过，检查上方报告详情"


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
