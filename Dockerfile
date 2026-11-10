# Stage 1: Build Frontend Single-Page App
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci || npm install

COPY frontend/ ./
RUN npm run build

# Stage 2: Python Backend Runtime
FROM python:3.11-slim
WORKDIR /app

# Install minimal system utilities (curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (lean production dependencies without heavy OCR models)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy Backend codebase and initial data
COPY backend/ ./backend/

# Copy built frontend assets so FastAPI mounts and serves it directly on single port
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Ensure runtime directories exist
RUN mkdir -p /app/backend/data/downloads /app/backend/data/uploads

ENV PORT=10000
ENV ENABLE_LOCAL_OCR=false
EXPOSE 10000

# Run FastAPI app with uvicorn (Render dynamically sets PORT)
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
