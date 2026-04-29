FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy source first — pyproject.toml uses src-layout, so editable
# installs require src/ to exist before pip runs.
COPY pyproject.toml .
COPY src/ src/
COPY profiles/ profiles/
COPY scripts/ scripts/

RUN pip install --no-cache-dir .

ENTRYPOINT ["bsim"]
