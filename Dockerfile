# Stage 1: Build Frontend (Vite + React + Tailwind)
FROM node:20-alpine AS frontend-builder
WORKDIR /app/web
COPY web/package.json ./
RUN npm install
COPY web/ ./
RUN npm run build

# Stage 2: Python Backend Runtime
FROM python:3.12-slim AS runner
WORKDIR /app

# Install system dependencies (Poppler & build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libpoppler-cpp-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code & advisory data
COPY casparser/ ./casparser/
COPY api/ ./api/
COPY data/ ./data/
COPY service.py market.py excel_exporter.py advisory.py consolidate.py blob_store.py ./

# Copy built frontend from Stage 1
COPY --from=frontend-builder /app/web/dist ./web/dist

ENV PYTHONUNBUFFERED=1
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
