# Start from an official Python 3.10 image.
# "slim" means it strips out things we don't need (docs, tests, build tools)
# to keep the container small. This is the "room" we're starting with.
FROM python:3.10-slim

# Set the working directory inside the container.
# All COPY and RUN commands below happen relative to this path.
# Think of it like `cd /app` — every command runs from here.
WORKDIR /app

# Tell Python not to write .pyc bytecode files inside the container.
# They add no value here — the container is never reused across runs.
ENV PYTHONDONTWRITEBYTECODE=1

# Install runtime dependencies by name, not via ".[api,db]".
# Why not ".[api,db]"? pyproject.toml has no package-discovery config pointing at
# prototype/, so pip install ".[api,db]" would install an empty shell of keystone
# alongside the real deps. We run from source (WORKDIR /app/prototype below), so
# pip only needs the dependencies — not the package itself.
RUN pip install --no-cache-dir \
    "fastapi>=0.110" \
    "uvicorn>=0.29" \
    "pydantic>=2" \
    "supabase>=2.31" \
    "python-dotenv>=1.0"

# Copy the application code AFTER pip install.
# Code changes invalidate only this layer, not the pip install layer above.
# prototype/ contains all our Python packages: keystone/, api/, and the run scripts.
COPY prototype/ ./prototype/

# Tell Docker our app will listen on port 8000.
# This is documentation only — it doesn't actually open the port.
# Fly.io reads fly.toml to know the port; EXPOSE just documents it here.
EXPOSE 8000

# Change into the prototype/ subdirectory so Python can find our packages.
# api/ and keystone/ both live under prototype/, so we must be inside it
# for `import api` and `import keystone` to resolve correctly.
WORKDIR /app/prototype

# Create and switch to a non-root user — Tier-1 hardening requirement.
# Containers run as root by default. If this process were ever compromised,
# root inside the container has far more power to cause damage.
# A dedicated appuser limits what an attacker can do.
# Must run as root (before USER) to create the user account.
RUN useradd --create-home appuser
USER appuser

# The command that runs when the container starts.
# uvicorn: the ASGI web server that runs FastAPI apps
# api.main:app: "look in api/main.py, find the object called app"
# --host 0.0.0.0: listen on all interfaces (127.0.0.1 is invisible outside Docker)
# --port 8000: must match internal_port in fly.toml and EXPOSE above
# --workers 1: one process — free tier has 256MB RAM; more workers = more memory
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

