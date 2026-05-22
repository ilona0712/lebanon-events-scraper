# Lebanese Events Scraper - Docker Configuration
# Uses Microsoft's official Playwright image (has all dependencies pre-installed)

FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
# playwright install chromium downloads the actual browser binary
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium

# Copy all scraper scripts
COPY events.py .
COPY news_holiday.py .
COPY convert.py .

# Create outputs directory
RUN mkdir -p outputs

# Run the main events scraper by default
# You can override this by running:
#   docker run --rm -v $(pwd)/outputs:/app/outputs <image> python news_holiday.py
#   docker run --rm -v $(pwd)/outputs:/app/outputs <image> python convert.py
CMD ["python", "events.py"]
