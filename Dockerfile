FROM python:3.11-slim-trixie

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pwm.py .
CMD ["python", "-u", "pwm.py"]