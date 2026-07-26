FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

# Install curl, git, nodejs, npm for zero-touch auto plugin setup
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    curl git nodejs npm ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies before copying source (preserves Docker layer cache)
COPY pyproject.toml ./
RUN python3 -c "import tomllib,subprocess,sys; f=open('pyproject.toml','rb'); deps=tomllib.load(f)['project']['dependencies']; f.close(); subprocess.run([sys.executable,'-m','pip','install','--no-cache-dir']+deps,check=True)"

COPY . /app

RUN chmod +x /app/docker-entrypoint.sh /app/scripts/setup.sh
RUN useradd --create-home --uid 1001 --shell /bin/bash appuser
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -sf http://localhost:8080/healthz || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]

