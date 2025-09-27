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
ENV PYTHONPATH=/app
ENV MPLBACKEND=Agg

# Command to run the analysis
CMD ["python", "modelling.py"]

# Optional: Expose a port if you want to serve results
# EXPOSE 8080