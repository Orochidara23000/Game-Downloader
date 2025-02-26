# Dockerfile
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy dependency file and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port that Gradio uses (7860 by default)
EXPOSE 7860

# Run the application
CMD ["python", "app.py"]
