# Use a slim Python image
FROM python:3.11-slim

# Install system dependencies and clean up apt cache in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install FFmpeg from a reliable source.
# We use a multi-stage approach: copy the ffmpeg binary from a trusted image.
FROM jrottenberg/ffmpeg:7.1-ubuntu2404 as ffmpeg-stage[citation:5]

FROM python:3.11-slim
# Copy only the ffmpeg and ffprobe binaries
COPY --from=ffmpeg-stage /usr/local/bin/ffmpeg /usr/local/bin/ffprobe /usr/local/bin/

# Verify the installation
RUN ffmpeg -version

# Set up the working directory
WORKDIR /app

# Copy Python dependencies file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY bot/ ./bot/
COPY docker/entrypoint.sh .

# Make the entrypoint script executable
RUN chmod +x /app/entrypoint.sh

# Create a non-root user to run the application (security best practice)
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

# Set the entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]
