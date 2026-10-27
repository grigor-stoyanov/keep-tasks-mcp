# Build from the repo root: docker build -f multiuser/Dockerfile .
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt requirements.txt
COPY multiuser/requirements.txt multiuser/requirements.txt
RUN pip install -r multiuser/requirements.txt
COPY src/ src/
COPY multiuser/ multiuser/
CMD ["python", "multiuser/main.py"]
