FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt ./
COPY dist/shared_lib-0.0.1.tar.gz /app/dist/shared_lib-0.0.1.tar.gz

RUN pip install --upgrade pip
RUN pip install psycopg2-binary
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "app.py"]