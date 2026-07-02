# Start from an official Python 3.10 image.
# "slim" means it strips out things we don't need (docs, tests, build tools)
# to keep the container small. This is the "room" we're starting with.

FROM python:3.10-slim

# Set the working directory inside the container.
# All COPY and RUN commands below happen relative to this path.
# Think of it like `cd /app` — every command runs from here.
WORKDIR /app

# Copy ONLY pyproject.toml first (before copying our code).
# Why? Docker builds in layers. If pyproject.toml hasn't changed,
# Docker reuses the cached "pip install" layer from last time — faster rebuilds.
COPY pyproject.toml .

# Install the dependencies our API needs.
# ".[api,db]" means: install this project + the "api" and "db" optional groups
#   api group: fastapi, uvicorn, pydantic
#   db group: supabase, python-dotenv
# --no-cache-dir: don't save the pip download cache (keeps the image smaller)
# Install runtime dependencies by name — NOT via ".[api,db]".
# Why not ".[api,db]"? pyproject.toml has no package-discovery config pointing at
# prototype/, so pip would install an empty shell of keystone alongside the real deps.
# We run from source (WORKDIR /app/prototype below), so pip only needs the imports —
# not the package itself. Listing deps explicitly makes that intent honest.
RUN pip install --no-cache-dir \
    "fastapi>=0.110" \
    "uvicorn>=0.29" \
    "pydantic>=2" \
    "supabase>=2.31" \
    "python-dotenv>=1.0"

# Now copy the actual application code.
# We do this AFTER pip install so code changes don't invalidate the pip cache layer.
# prototype/ contains all our Python packages: keystone/, api/, and the run scripts.
COPY prototype/ ./prototype/

# Tell Docker our app will listen on port 8000.
# This is documentation only — it doesn't actually open the port.
# Fly.io reads this to know which port to route traffic to.
EXPOSE 8000

# Change into the prototype/ subdirectory so Python can find our packages.
# When Python looks for `import api` it searches the current directory first.
# api/ and keystone/ both live under prototype/, so we must be inside it.
WORKDIR /app/prototype

# Create and switch to a non-root user — Tier-1 hardening requirement.
# Containers run as root by default. If this process were ever compromised,
# root inside the container has far more power to cause damage.
# A dedicated appuser limits what an attacker can do.
# Must run as root (before USER) to create the user account.
RUN useradd --create-home appuser
USER appuser

# The command that runs when the container starts.
# uvicorn: the web server that runs our FastAPI app
# api.main:app: "in the file api/main.py, find the variable called app"
# --host 0.0.0.0: listen on ALL network interfaces (not just localhost).
#   Inside Docker, 127.0.0.1 is invisible to the outside world.
#   0.0.0.0 means "accept connections from anywhere" — required for Fly to reach us.
# --port 8000: the port to listen on (matches EXPOSE above and fly.toml below)
# --workers 1: run one worker process. Free tier has 256MB RAM; more workers = more memory.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

