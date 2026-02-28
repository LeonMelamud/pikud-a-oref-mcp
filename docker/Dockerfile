# 1. Use an official Python runtime as a parent image
FROM python:3.11-slim

# 2. Set the working directory in the container
WORKDIR /app

# 3. Copy the dependencies file to the working directory
COPY requirements.txt .

# 4. Install any needed dependencies specified in requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 5. Copy the application code into the container
COPY . .

# 6. Create non-root user and data directory
RUN useradd --create-home appuser && \
    mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser

ENV PORT=8000

# 7. Expose the port the app runs on
EXPOSE ${PORT}

# 8. Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\",\"8000\")}/health')" || exit 1

# 9. Define the command to run the app
CMD uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT}