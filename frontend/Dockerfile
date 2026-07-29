# 1. Build Stage
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

# 2. Runtime Stage — nginx.
# `serve -s`는 확장자 없는 경로를 실제 파일 존재 여부와 무관하게 전부 index.html로
# rewrite해(vercel/serve의 applyRewrites 동작), Vue Router 새로고침 404는 고치지만
# public/presentation/ 같은 순수 정적 서브패스 접근을 막는 부작용이 있었다. nginx의
# try_files는 "실제 파일/디렉토리 → 없으면 index.html" 순서로 시도해 두 요구를 함께 만족한다.
FROM nginx:alpine AS runner

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 5173

CMD ["nginx", "-g", "daemon off;"]
