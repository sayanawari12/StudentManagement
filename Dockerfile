# Student Management System — production Docker image
# Base: python:3.12-slim (minimal Debian, no dev tools)
FROM python:3.12-slim

# Set working directory
WORKDIR /app

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
