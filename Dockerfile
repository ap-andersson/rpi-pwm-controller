FROM python:3.11-slim-bookworm

WORKDIR /app

# Install gpiod for modern GPIO control
RUN apt-get update && \
    apt-get install -y gpiod && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pwm.py .
CMD ["python", "-u", "pwm.py"]