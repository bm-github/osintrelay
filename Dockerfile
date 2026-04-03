# Main Dockerfile for OSINT Relay - supports both CLI and bot modes
# 
# Build:
#   docker build -t osint-relay .
#
# Run CLI:
#   docker run --rm -it -v $(pwd)/data:/app/data -v $(pwd)/logs:/app/logs \
#     --env-file .env osint-relay
#
# Run with stdin JSON input:
#   docker run --rm -v $(pwd)/data:/app/data -v $(pwd)/logs:/app/logs \
#     --env-file .env osint-relay --stdin < query.json

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY socialosintagent/ ./socialosintagent/

# Create necessary directories with proper permissions
RUN mkdir -p /app/data /app/data/cache /app/data/media /app/data/outputs /app/data/sessions /app/logs \
    && chmod 755 /app/data /app/logs

# Create non-root user for security
RUN useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Default entrypoint - can be overridden
ENTRYPOINT ["python", "-m", "socialosintagent.main"]

# Default command
CMD []