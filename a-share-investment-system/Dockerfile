FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt* pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null || \
    pip install --no-cache-dir -e . 2>/dev/null || \
    pip install --no-cache-dir fastapi uvicorn sqlalchemy akshare pandas numpy rich

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p data logs reports backups

# Expose port
EXPOSE 8765

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/api/system/health')" || exit 1

# Start server
CMD ["python", "main.py", "serve"]
