# Use Ubuntu 22.04 as base image for maximum compatibility
# This supports both x86-64 and arm64 architectures
FROM ubuntu:22.04

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    wget \
    curl \
    git \
    # Playwright dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libxcb1 \
    libxss1 \
    libgtk-3-0 \
    libgdk-pixbuf2.0-0 \
    libcairo-gobject2 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libxshmfence1 \
    fonts-liberation \
    libappindicator3-1 \
    libnss3-tools \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment
RUN python3 -m venv $VIRTUAL_ENV

# Upgrade pip and install dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r /tmp/requirements.txt


# Create a non-root user for security and Playwright compatibility
RUN useradd -m -s /bin/bash crawler && \
    chown -R crawler:crawler $VIRTUAL_ENV

# Install Playwright browsers and dependencies as the crawler user
USER crawler
RUN playwright install

# Switch back to root to copy files and set permissions
USER root

# Create app directory and set ownership
RUN mkdir -p /app && chown -R crawler:crawler /app
WORKDIR /app

# Copy application code
COPY . /app/
RUN chown -R crawler:crawler /app

# Switch back to crawler user for running the application
USER crawler

# Expose port
EXPOSE 8000

# Default command
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]
