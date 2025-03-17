FROM python:latest

EXPOSE 5000/tcp

WORKDIR /app

COPY src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update -y && apt-get install iputils-ping -y

COPY src/ .

CMD ["python", "app.py"]
