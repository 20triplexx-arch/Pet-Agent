FROM node:24-alpine AS frontend
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
FROM python:3.13-slim
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY LICENSE UPSTREAM.md /app/
COPY --from=frontend /web/dist /app/frontend/dist
RUN useradd --uid 10001 --create-home chongban && mkdir -p /app/backend/storage && chown -R chongban:chongban /app
USER chongban
ENV DATABASE_URL=sqlite:////app/backend/storage/chongban.db
EXPOSE 8000
CMD ["sh","-c","python -m scripts.init_db && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]

