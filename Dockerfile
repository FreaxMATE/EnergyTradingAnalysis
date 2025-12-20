# Use official Python runtime as base image
FROM python:3.11-slim

# Set working directory in container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create directory for output files
RUN mkdir -p /app/output

# Set environment variables
ENV PYTHONPATH=/app/src
ENV MPLBACKEND=Agg

# Expose port for Dash dashboard
EXPOSE 8050

# Default command runs the interactive dashboard
# Override with docker run arguments for other modes
CMD ["python", "src/main.py", "plot"]