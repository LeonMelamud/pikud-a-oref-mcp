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

# 6. Expose the port the app runs on for the host machine
EXPOSE 8001

# 7. Define the command to run the app
# Add a startup delay to give the main app time to initialize
CMD ["sh", "-c", "sleep 5 && python -m src.core.mcp_server"] 