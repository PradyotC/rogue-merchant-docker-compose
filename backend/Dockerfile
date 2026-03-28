# ═══════════════════════════════════════════════════════════════
# STAGE 1: The Builder
# ═══════════════════════════════════════════════════════════════
FROM python:3.10-slim AS builder

# Stop Python from generating .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create a virtual environment
RUN python -m venv /opt/venv

# Activate the virtual environment so pip installs into it
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies into the venv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ═══════════════════════════════════════════════════════════════
# STAGE 2: The Runner (Final Image)
# ═══════════════════════════════════════════════════════════════
FROM python:3.10-slim

# Keep Python behaving nicely in the container
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy ONLY the compiled virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Activate the virtual environment in this new stage
ENV PATH="/opt/venv/bin:$PATH"

# Copy your actual game logic
COPY app.py .

# Expose the port
EXPOSE 5000

# Run the Flask app
CMD ["python", "app.py"]