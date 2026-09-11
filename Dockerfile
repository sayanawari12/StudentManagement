# Student Management System — production Docker image
# Base: python:3.12-slim (minimal Debian, no dev tools)
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies:
#   default-mysql-client  →  provides the mysql and mysqladmin CLI tools
#                             used by docker-entrypoint.sh to apply schema.sql
#                             and wait for MySQL readiness.
#   (mysql-connector-python is a pure-Python driver and does NOT ship these tools)
RUN apt-get update && \
    apt-get install -y --no-install-recommends default-mysql-client && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies (production only — no pytest)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy and make the entrypoint script executable
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Expose the application port
EXPOSE 5000

# Use the entrypoint script to apply DB schema/seed, then start gunicorn
ENTRYPOINT ["/docker-entrypoint.sh"]
