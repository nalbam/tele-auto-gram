FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create data directory
RUN mkdir -p data

# Expose port for web UI
EXPOSE 5000

# Run the application
CMD ["python", "main.py"]
