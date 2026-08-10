# 臻护前端镜像 —— 多阶段构建
# 构建上下文: apps/frontend (docker compose build 自动处理)
# 阶段1: Node 构建
FROM node:22-alpine AS build

WORKDIR /app

COPY package.json ./
# 无 package-lock.json 时使用 install; 若后续补充 lock 可换 npm ci
RUN npm install

COPY . .

# tsc -b && vite build → dist/
RUN npm run build

# 阶段2: Nginx 静态托管 + API 代理
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
