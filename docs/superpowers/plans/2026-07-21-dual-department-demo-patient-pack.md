# 双科室演示病例包 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清理受控历史演示状态，并在心内科和呼吸科各写入 10 个可复现、可跨三端演示的虚构临床病例。

**Architecture:** 后端建立唯一的演示病例目录和状态构建器，通过现有 `patient_states` 与角色/科室访问过滤为三端提供同一数据。管理端调用受审计的重置端点，先按演示元数据和旧 fixture 白名单清理关联状态，再原子写入 20 个患者；前端仅增加受权限控制的操作入口与查询缓存失效。

**Tech Stack:** FastAPI、SQLAlchemy、现有状态存储、React、TypeScript、TanStack Query、MUI、pytest、Vitest、Playwright。

---

### Task 1: 演示状态清理与病例目录契约

**Files:**
- Modify: `services/inpatient-ward/src/zhenhu/inpatient/routes/patient_fixtures.py`
- Create: `services/inpatient-ward/tests/test_demo_patient_pack.py`

- [ ] **Step 1: 编写会失败的病例目录契约测试**

```python
from zhenhu.inpatient.routes.patient_fixtures import DEMO_PATIENT_PACK, build_demo_patient_states


def test_demo_pack_contains_ten_patients_per_department():
    assert len(DEMO_PATIENT_PACK["心内科"]) == 10
    assert len(DEMO_PATIENT_PACK["呼吸科"]) == 10
    states = build_demo_patient_states()
    assert len(states) == 20
    assert all(state["demo_seed"] is True for state in states.values())
    assert {state["department"] for state in states.values()} == {"心内科", "呼吸科"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest services/inpatient-ward/tests/test_demo_patient_pack.py::test_demo_pack_contains_ten_patients_per_department -q`

Expected: FAIL，因为演示病例目录与构建函数尚不存在。

- [ ] **Step 3: 实现集中病例目录和状态构建器**

```python
DEMO_PACK_VERSION = "2026-07-21.1"
DEMO_PATIENT_IDS = (
    "demo-card-hf-acute", "demo-card-post-pci", "demo-card-af-anticoag",
    "demo-card-htn-crisis", "demo-card-hf-handoff", "demo-card-chest-pain",
    "demo-card-acs-monitor", "demo-card-cardiorenal", "demo-card-pacemaker",
    "demo-card-hf-followup", "demo-resp-copd-ae", "demo-resp-cap",
    "demo-resp-asthma", "demo-resp-pe", "demo-resp-sepsis-recovery",
    "demo-resp-ild-oxygen", "demo-resp-bronchiectasis", "demo-resp-chemo-infection",
    "demo-resp-osa-copd", "demo-resp-copd-followup",
)
DEMO_PATIENT_PACK = {
    "心内科": CARDIOLOGY_PATIENTS,
    "呼吸科": RESPIRATORY_PATIENTS,
}


def build_demo_patient_states() -> dict[str, dict]:
    return {
        item["patient_id"]: {
            **deepcopy(item["state"]),
            "patient_id": item["patient_id"],
            "department": department,
            "demo_seed": True,
            "demo_pack_version": DEMO_PACK_VERSION,
            "demo_department": department,
        }
        for department, entries in DEMO_PATIENT_PACK.items()
        for item in entries
    }
```

每例必须包含虚构身份与联系方式、病种模板、阶段、风险、至少一项可展示的体征/检验、护理/查房/审核/出院/随访中与该场景匹配的状态。保留旧 fixture 常量仅用于受控迁移清理和旧测试兼容。

- [ ] **Step 4: 运行病例目录测试**

Run: `python -m pytest services/inpatient-ward/tests/test_demo_patient_pack.py -q`

Expected: PASS。

### Task 2: 后端受控重置端点与审计

**Files:**
- Modify: `services/inpatient-ward/src/zhenhu/inpatient/routes/admin.py`
- Modify: `services/inpatient-ward/src/zhenhu/inpatient/services/management_access.py`
- Modify: `services/inpatient-ward/src/zhenhu/inpatient/routes/patient_fixtures.py`
- Modify: `services/inpatient-ward/tests/test_demo_patient_pack.py`

- [ ] **Step 1: 编写会失败的路由测试**

```python
@pytest.mark.asyncio
async def test_demo_reset_requires_management_permission(client):
    response = await client.post("/inpatient/fixtures/reset-demo", headers={"x-role": "doctor"})
    assert response.status_code in {401, 403}


@pytest.mark.asyncio
async def test_demo_reset_replaces_only_demo_records(client, isolated_state_store):
    headers = {"x-role": "doctor", "x-title": "科主任", "x-department": quote("心内科")}
    response = await client.post("/inpatient/fixtures/reset-demo", headers=headers, json={"confirmed": True})
    assert response.status_code == 200
    assert response.json()["data"]["total"] == 20
    assert response.json()["data"]["by_department"] == {"心内科": 10, "呼吸科": 10}
```

- [ ] **Step 2: 运行路由测试确认失败**

Run: `python -m pytest services/inpatient-ward/tests/test_demo_patient_pack.py -q`

Expected: FAIL，因为 `reset-demo` 路由、能力项和清理服务尚不存在。

- [ ] **Step 3: 实现白名单清理与幂等重置**

```python
async def reset_demo_patient_pack(request: Request, payload: DemoResetRequest) -> UnifiedResponse:
    require_management_operation(request, "demo_patient_reset")
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="Explicit confirmation is required.")
    if is_production_environment():
        raise HTTPException(status_code=403, detail="Demo reset is disabled in production.")
    removed_ids = await clear_demo_patient_records()
    states = build_demo_patient_states()
    for patient_id, state in states.items():
        set_state(patient_id, state)
    audit_id = await write_management_audit_event(
        action_type="demo_patient_pack_reset",
        detail={"removed": len(removed_ids), "total": 20, "by_department": {"心内科": 10, "呼吸科": 10}},
        request=request,
    )
    return UnifiedResponse(data={"total": 20, "by_department": {"心内科": 10, "呼吸科": 10}, "removed": len(removed_ids), "audit_id": audit_id})
```

`clear_demo_patient_records` 必须从状态存储读取 `demo_seed`/`demo_pack_version` 元数据，合并固定的旧 fixture ID 白名单，删除对应热状态、事务投影与 Agent Loop。禁止对共享表使用无条件 `DELETE` 或表截断。

- [ ] **Step 4: 验证端点权限、生产禁用与重复执行**

Run: `python -m pytest services/inpatient-ward/tests/test_demo_patient_pack.py -q`

Expected: PASS，覆盖未授权、未确认、生产环境拒绝、20 例重建、重置幂等和保留非演示状态。

### Task 3: 三端状态投影回归

**Files:**
- Modify: `services/inpatient-ward/tests/test_demo_patient_pack.py`
- Modify: `services/inpatient-ward/tests/test_dashboard_care_fixture.py`

- [ ] **Step 1: 编写三端读取回归测试**

```python
@pytest.mark.asyncio
async def test_reseeded_cases_appear_in_doctor_nurse_and_management_views(client, isolated_state_store):
    await reset_demo(client)
    doctor = await client.get("/ward/patients", headers=doctor_headers("心内科"))
    nurse = await client.get("/nurse/board", headers=nurse_headers("呼吸科"))
    management = await client.get("/ward/overview", headers=manager_headers("心内科"))
    assert len(doctor.json()["data"]["patients"]) == 10
    assert nurse.json()["data"]["patients"]
    assert management.json()["data"]["total_patients"] == 10
```

- [ ] **Step 2: 运行回归测试并根据真实响应字段修正断言**

Run: `python -m pytest services/inpatient-ward/tests/test_demo_patient_pack.py services/inpatient-ward/tests/test_dashboard_care_fixture.py -q`

Expected: PASS，现有单病例 fixture 不再作为三端演示数据源。

- [ ] **Step 3: 运行关键后端回归**

Run: `python -m pytest services/inpatient-ward/tests/test_patient_access.py services/inpatient-ward/tests/test_management_operations.py services/inpatient-ward/tests/test_follow_up_overview.py -q`

Expected: PASS。

### Task 4: 管理端“重置演示患者”入口

**Files:**
- Modify: `apps/frontend/src/services/admin-service.ts`
- Modify: `apps/frontend/src/services/admin-service.test.ts`
- Modify: `apps/frontend/src/components/admin/SystemOperationsPanel.tsx`
- Create: `apps/frontend/src/components/admin/SystemOperationsPanel.test.tsx`

- [ ] **Step 1: 编写会失败的服务与组件测试**

```tsx
it('posts an explicitly confirmed demo reset through the audited endpoint', async () => {
  await resetDemoPatients();
  expect(fetchMock.mock.calls[0][0]).toContain('/inpatient/fixtures/reset-demo');
  expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({ confirmed: true });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `npm --workspace apps/frontend run test:run -- src/services/admin-service.test.ts`

Expected: FAIL，因为服务方法和运维项不存在。

- [ ] **Step 3: 实现服务、能力项和二次确认反馈**

```ts
export const resetDemoPatients = () => apiPost<DemoResetResult>(
  '/inpatient/fixtures/reset-demo', { confirmed: true }, undefined,
  { 'Idempotency-Key': operationKey('demo-patient-reset') },
);
```

在 `OPERATIONS` 增加 `demo_patient_reset`：文案明确为清理并重建 20 名虚构病例；操作成功后失效 `ward`、`nurse`、`inpatient`、`follow-up`、`dashboard` 与 `admin` 查询键，展示审计号、清理数和按科室写入数。

- [ ] **Step 4: 运行前端单元测试与构建**

Run: `npm --workspace apps/frontend run test:run -- src/services/admin-service.test.ts src/components/admin/SystemOperationsPanel.test.tsx && npm --workspace apps/frontend run build`

Expected: tests PASS，TypeScript 与 Vite 构建成功。

### Task 5: 运行时清理、重建与浏览器验证

**Files:**
- Modify: `docs/臻护全流程项目开发文档/臻护-代码现状基线.md`

- [ ] **Step 1: 启动服务并确认单一端口约定**

Run: `GET http://127.0.0.1:8000/health` and `GET http://127.0.0.1:5173/`

Expected: 后端健康、前端可访问，Vite 代理目标为 `127.0.0.1:8000`。

- [ ] **Step 2: 以管理身份执行一次真实重置**

Run: `POST /inpatient/fixtures/reset-demo` with `{ "confirmed": true }`

Expected: 返回 `total: 20`，心内科与呼吸科均为 10，包含审计号。

- [ ] **Step 3: 浏览器验证三端场景**

Run: 打开医生工作台、护理工作台与管理端，依次筛选心内科与呼吸科并进入患者详情。

Expected: 每科 10 例，患者链接有效；至少分别看到预警、待审核、护理任务、出院交接和异常随访；无 4xx/5xx 或空白页面。

- [ ] **Step 4: 更新运行基线与提交**

```markdown
演示患者：心内科 10 例 + 呼吸科 10 例；仅在开发/演示环境由管理端受审计重置。
```

Run: `git diff --check` and the focused backend/frontend test commands above.

Expected: 无空白错误、测试通过，仅提交本功能涉及文件。
