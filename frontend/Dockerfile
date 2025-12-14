# React/Vite Frontend Dockerfile
FROM node:20-alpine

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 파일 복사 및 설치 (캐싱 효율을 위해 먼저 복사)
COPY package.json package-lock.json* ./
RUN npm install

# 소스 코드 복사
COPY . .

# 포트 노출 (Vite 기본 포트 5173, 또는 3000)
EXPOSE 3000

# 개발 모드 실행 (외부 접속 가능하도록 --host 옵션 사용)
CMD ["npm", "run", "dev", "--", "--host", "--port", "3000"]

