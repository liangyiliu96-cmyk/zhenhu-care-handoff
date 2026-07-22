# 医生临床副驾驶一期 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为医生工作台提供可追溯的查房预读、增量病程草稿和病史缺口引导，同时不改变既有临床审核和写入边界。

**Architecture:** 后端从当前患者 state 构造带来源的事实快照，规则产生预读和病史缺口；可选 LLM 仅润色受支持事实，Harness 拒绝无来源文本。前端在既有查房和入院采集面板中展示并复用既有 round edit/review 和 history write 接口。

**Tech Stack:** FastAPI、Pydantic v2、现有 PatientAgentLoop/DeepAgent/Harness、React、TanStack Query、MUI、Vitest、pytest。

---

### Task 1: 建立事实快照与确定性预读

**Files:**
- Create: `services/inpatient-ward/src/zhenhu/inpatient/services/doctor_copilot.py`
- Create: `services/inpatient-ward/tests/test_doctor_copilot.py`

- [ ] **Step 1: 写出失败测试**

```python
def test_build_pre_round_brief_only_exposes_current_patient_facts():
    brief = build_pre_round_brief({
        "patient_id": "p-1", "state_version": 4,
        "vital_signs": [{"timestamp": "2026-07-22T08:00:00Z", "heart_rate": 110}],
        "lab_results": [{"name": "肌酐", "value": "155", "timestamp": "2026-07-22T07:00:00Z"}],
        "clinical_alerts": [{"message": "心率增快", "status": "active"}],
    })
    assert brief["state_version"] == 4
    assert all(item["facts"] for item in brief["attention_items"])
    assert "p-2" not in str(brief)
```

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest tests/test_doctor_copilot.py -q`

Expected: FAIL because `doctor_copilot` does not exist.

- [ ] **Step 3: 实现最小事实快照与规则预读**

```python
def fact(source_type: str, source_id: str, observed_at: str, field: str, value: object) -> dict:
    return {"source_type": source_type, "source_id": source_id, "observed_at": observed_at, "field": field, "value": value}

def build_pre_round_brief(state: dict) -> dict:
    return {
        "patient_id": state["patient_id"],
        "state_version": int(state.get("state_version", 0)),
        "attention_items": build_attention_items(state),
        "history_gaps": build_history_gaps(state),
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_doctor_copilot.py -q`

Expected: PASS.

### Task 2: 生成受事实支持的增量 SOAP 草稿

**Files:**
- Modify: `services/inpatient-ward/src/zhenhu/inpatient/services/doctor_copilot.py`
- Modify: `services/inpatient-ward/src/zhenhu/inpatient/agent/harness.py`
- Modify: `services/inpatient-ward/tests/test_doctor_copilot.py`

- [ ] **Step 1: 写出无来源文本被拒绝的失败测试**

```python
def test_progress_note_draft_marks_unsupported_sections_as_needing_input():
    draft = build_progress_note_draft({"patient_id": "p-1", "state_version": 2})
    assert draft["sections"]["assessment"]["status"] == "needs_input"
    assert draft["sections"]["assessment"]["text"] == "待医生补充"
```

- [ ] **Step 2: 实现草稿 schema 和 Harness 对账**

```python
def supported_section(text: str, facts: list[dict]) -> dict:
    if not facts:
        return {"text": "待医生补充", "status": "needs_input", "facts": []}
    return {"text": text, "status": "draft", "facts": facts}
```

- [ ] **Step 3: 可选接入 LLM 润色与确定性降级**

```python
candidate = await deep_invoke(provider, prompt, caller="progress_note_draft", timeout=15.0)
draft = validate_supported_progress_note(candidate, facts) if candidate else deterministic_draft(facts)
```

- [ ] **Step 4: 运行后端定向测试**

Run: `python -m pytest tests/test_doctor_copilot.py tests/test_clinical_evidence.py -q`

Expected: PASS.

### Task 3: 暴露患者级医生副驾驶接口

**Files:**
- Create: `services/inpatient-ward/src/zhenhu/inpatient/routes/doctor_copilot.py`
- Modify: `services/inpatient-ward/src/zhenhu/inpatient/main.py`
- Modify: `services/inpatient-ward/tests/test_doctor_copilot.py`

- [ ] **Step 1: 写路由契约测试**

```python
response = client.get("/inpatient/p-1/doctor-copilot/pre-round")
assert response.status_code == 200
assert response.json()["data"]["state_version"] == 4
```

- [ ] **Step 2: 实现只读预读和草稿生成接口**

```python
@router.get("/{patient_id}/doctor-copilot/pre-round")
async def get_pre_round(patient_id: str):
    state = await patient_state_service.read(patient_id)
    return UnifiedResponse(data=build_pre_round_brief(state))
```

- [ ] **Step 3: 增加权限、患者范围和版本校验测试**

Run: `python -m pytest tests/test_doctor_copilot.py -q`

Expected: PASS.

### Task 4: 接入前端查房与病史采集

**Files:**
- Create: `apps/frontend/src/services/doctor-copilot-service.ts`
- Create: `apps/frontend/src/components/clinical/PreRoundBriefPanel.tsx`
- Create: `apps/frontend/src/components/clinical/HistoryGapGuide.tsx`
- Modify: `apps/frontend/src/components/clinical/RoundsManagementPanel.tsx`
- Modify: `apps/frontend/src/components/clinical/ClinicalIntakePanel.tsx`
- Create: `apps/frontend/src/components/clinical/PreRoundBriefPanel.test.tsx`

- [ ] **Step 1: 写失败的组件测试**

```tsx
render(<PreRoundBriefPanel brief={brief} onGenerateDraft={vi.fn()} />)
expect(screen.getByText("查房前预读")).toBeInTheDocument()
expect(screen.getByText("心率增快")).toBeInTheDocument()
```

- [ ] **Step 2: 实现 API client 和查询失效策略**

```ts
export const fetchPreRoundBrief = (patientId: string) => apiGet<PreRoundBrief>(`/inpatient/${patientId}/doctor-copilot/pre-round`)
```

- [ ] **Step 3: 连接查房面板和既有编辑/核对入口**

```tsx
<PreRoundBriefPanel brief={brief.data} onGenerateDraft={() => draftMutation.mutate()} />
```

- [ ] **Step 4: 在病史弹窗显示确定性缺口，不阻断录入**

```tsx
<HistoryGapGuide gaps={brief.data?.history_gaps ?? []} />
```

- [ ] **Step 5: 运行前端定向测试**

Run: `npm run test:run -- PreRoundBriefPanel.test.tsx`

Expected: PASS.

### Task 5: 集成验证与文档收口

**Files:**
- Modify: `docs/臻护全流程项目开发文档/臻护-Agent全流程、Loop Harness与DeepAgent实战手册.md`

- [ ] **Step 1: 跑后端、类型和 lint 检查**

Run:

```bash
python -m pytest tests/test_doctor_copilot.py -q
npm run build
npm run lint
```

Expected: all commands exit 0.

- [ ] **Step 2: 浏览器验证医生真实流程**

Run: 使用演示患者打开 `?section=rounds`，确认预读、草稿、编辑和核对可完成，且控制台无错误。

- [ ] **Step 3: 更新 Agent 手册并提交**

```bash
git add services/inpatient-ward apps/frontend docs
git commit -m "feat: add doctor copilot pre-round workflow"
```
