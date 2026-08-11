"""臻护 OIDC 统一鉴权验证脚本 —— 供前端 QA / 联调复用。

用法（Keycloak 已启动, 4 服务已以 AUTH_MODE=oidc 启动）:
    python scripts/verify_oidc_auth.py
    python scripts/verify_oidc_auth.py --base http://localhost:8080 --username doctor --password doctor123

默认检查:
  - Keycloak realm 健康 (GET /realms/zhenhu)
  - direct access grant 获取 access_token
  - 对每个服务受保护端点: 无 token → 401, 伪造 token → 401, 有效 token → 200/非401

Token 获取方式（供前端 QA 复用）:
  curl -s -X POST http://localhost:8080/realms/zhenhu/protocol/openid-connect/token \
    -d "grant_type=password&client_id=zhenhu-web&username=doctor&password=doctor123" \
    | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])"
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx

DEFAULT_SERVICES = [
    {"name": "workflow-engine", "base": "http://localhost:8100", "path": "/cases/"},
    {"name": "knowledge-orchestrator", "base": "http://localhost:8200", "path": "/knowledge/documents"},
    {"name": "fhir-adapter", "base": "http://localhost:8300", "path": "/fhir/Patient/pat-demo-001"},
    {"name": "inpatient-ward", "base": "http://localhost:8001", "path": "/health"},
]


def fetch_token(base: str, realm: str, client_id: str, username: str, password: str) -> str:
    """direct access grant 获取 access_token。"""
    url = f"{base}/realms/{realm}/protocol/openid-connect/token"
    resp = httpx.post(
        url,
        data={
            "grant_type": "password",
            "client_id": client_id,
            "username": username,
            "password": password,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    return str(resp.json()["access_token"])


def main() -> int:
    parser = argparse.ArgumentParser(description="臻护 OIDC 统一鉴权验证")
    parser.add_argument("--base", default="http://localhost:8080", help="Keycloak 宿主地址")
    parser.add_argument("--realm", default="zhenhu")
    parser.add_argument("--client-id", default="zhenhu-web")
    parser.add_argument("--username", default="doctor")
    parser.add_argument("--password", default="doctor123")
    parser.add_argument("--auth-mode-path", default="/health", help="验证 AUTH_MODE 时使用的免认证端点")
    args = parser.parse_args()

    # 1. Keycloak realm 健康
    try:
        resp = httpx.get(f"{args.base}/realms/{args.realm}", timeout=10.0)
        resp.raise_for_status()
        realm_info = resp.json()
        print(f"[Keycloak] realm {args.realm} 健康: realm={realm_info.get('realm')} enabled={realm_info.get('enabled')}")
    except Exception as exc:  # noqa: BLE001
        print(f"[Keycloak] FAIL realm 不可达: {exc}")
        return 1

    # 2. 获取 token
    try:
        token = fetch_token(args.base, args.realm, args.client_id, args.username, args.password)
        print(f"[Token] 获取成功 ({args.username}), access_token 长度={len(token)}")
    except Exception as exc:  # noqa: BLE001
        print(f"[Token] FAIL direct access grant 获取失败: {exc}")
        return 1

    fake_token = "not.a.real.token"

    # 3. 逐服务验证 401/200
    failed = False
    print("\n服务鉴权检查:")
    for svc in DEFAULT_SERVICES:
        url = svc["base"] + svc["path"]
        results = []
        try:
            r_no = httpx.get(url, timeout=10.0)
            results.append(("无token", r_no.status_code, "401" if r_no.status_code == 401 else "FAIL"))
        except Exception as exc:  # noqa: BLE001
            results.append(("无token", "ERR", str(exc)))

        try:
            r_fake = httpx.get(url, headers={"Authorization": f"Bearer {fake_token}"}, timeout=10.0)
            results.append(("伪造token", r_fake.status_code, "401" if r_fake.status_code == 401 else "FAIL"))
        except Exception as exc:  # noqa: BLE001
            results.append(("伪造token", "ERR", str(exc)))

        try:
            r_ok = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=10.0)
            ok = r_ok.status_code not in (401, 403)
            results.append(("有效token", r_ok.status_code, "OK" if ok else "FAIL"))
        except Exception as exc:  # noqa: BLE001
            results.append(("有效token", "ERR", str(exc)))

        line = f"  {svc['name']:<22} {svc['path']:<40}"
        for label, code, verdict in results:
            line += f" | {label}:{code}({verdict})"
        print(line)
        if any(verdict == "FAIL" or code == "ERR" for _, code, verdict in results):
            failed = True

    # 4. 白名单端点免认证
    try:
        r_public = httpx.get(DEFAULT_SERVICES[0]["base"] + args.auth_mode_path, timeout=10.0)
        public_ok = r_public.status_code == 200
        print(f"\n[白名单] {args.auth_mode_path} 免认证: {'OK' if public_ok else 'FAIL'} ({r_public.status_code})")
        if not public_ok:
            failed = True
    except Exception as exc:  # noqa: BLE001
        print(f"[白名单] FAIL: {exc}")
        failed = True

    print(f"\n结果: {'全部通过' if not failed else '存在失败'}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
