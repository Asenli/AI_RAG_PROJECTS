# ============================================================
#  Stage 1: Build Vue 3 + Vite frontend
# ============================================================
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/node:20-alpine AS builder

WORKDIR /build

# Install dependencies
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --silent

# Copy source and build
COPY frontend/ .
RUN npm run build

# ============================================================
#  Stage 2: Nginx serve + API reverse proxy
# ============================================================
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/nginx:alpine

# Remove default config
RUN rm -f /etc/nginx/conf.d/default.conf

# Copy custom Nginx config
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy built frontend from builder stage
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
