# kb-qa-agent frontend — 多阶段镜像
# 阶段 1：node 构建
# 阶段 2：nginx 静态服务 + /v1 /health 反代到 backend service

FROM node:24-alpine AS builder
WORKDIR /app

# 启用 corepack pnpm（package.json 用的是 pnpm）
RUN corepack enable && corepack prepare pnpm@latest --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# ----------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
