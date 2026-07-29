FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
COPY .env ./
RUN npm install

COPY . .
RUN npm run build

# 정적 파일 서빙용 경량 패키지 글로벌 설치
RUN npm install -g serve

EXPOSE 5173

CMD ["serve", "dist", "-l", "5173"]
