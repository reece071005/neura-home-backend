FROM python:3.11-slim



RUN apt-get update && apt-get install -y build-essential libffi-dev ffmpeg && rm -rf /var/lib/apt/lists/*


WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .


# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
