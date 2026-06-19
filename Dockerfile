FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

# Install curl for healthcheck
RUN apt-get update -qq && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install dependencies before copying source (preserves Docker layer cache)
COPY pyproject.toml ./
RUN python3 -c "import tomllib,subprocess,sys; f=open('pyproject.toml','rb'); deps=tomllib.load(f)['project']['dependencies']; f.close(); subprocess.run([sys.executable,'-m','pip','install','--no-cache-dir']+deps,check=True)"

COPY . /app

RUN useradd --create-home --uid 1001 --shell /bin/bash appuser
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -sf http://localhost:8080/healthz || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--loop", "asyncio", "--http", "h11"]
