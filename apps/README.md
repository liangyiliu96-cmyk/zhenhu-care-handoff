# 前端应用

正式前端位于 `apps/frontend`，使用 React、Vite、MUI 和 TypeScript。

## 本地入口

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8001`
- 代理：`5173 -> 8001`

```bash
cd apps/frontend
npm install
npm run dev -- --host 127.0.0.1
```

前端 API 请求保持同源路径，由 [vite.config.ts](frontend/vite.config.ts) 转发到 `VITE_DEV_API_TARGET`。默认目标为 `http://127.0.0.1:8001`。

```bash
npm run lint
npm run build
npm run test:run
```

不要把容器内部的 `8000` 作为浏览器或本机脚本访问地址。
