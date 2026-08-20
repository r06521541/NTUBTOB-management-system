FROM python:3.10-slim
WORKDIR /app
COPY apps/mobile_staging_broker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
CMD ["gunicorn", "--bind", ":8080", "--workers", "1", "--threads", "1", "apps.mobile_staging_broker.bootstrap:app"]
