FROM python:3.11-slim

# Install system dependencies (THIS FIXES ALL YOUR FFmpeg ISSUES)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 10000

# Start server
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000"]
