# locust/Dockerfile
FROM python:3.10-slim

WORKDIR /locust

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8089

CMD ["locust", "-f", "locustfile.py", "--host", "http://service:8000"]
