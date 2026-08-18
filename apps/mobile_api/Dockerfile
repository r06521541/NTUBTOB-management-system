FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt ./
COPY dist/ ./dist/
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./
CMD exec gunicorn --bind :${PORT:-8080} --workers 1 --threads 8 'bootstrap:app'
