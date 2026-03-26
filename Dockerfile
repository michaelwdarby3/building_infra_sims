FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir .

# Copy source
COPY src/ src/
COPY profiles/ profiles/
COPY scripts/ scripts/

RUN pip install --no-cache-dir -e .

ENTRYPOINT ["bsim"]
