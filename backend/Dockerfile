FROM python:3.14-slim

RUN groupadd --system reliefmesh \
    && useradd --system --gid reliefmesh --create-home --home-dir /home/reliefmesh reliefmesh

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=reliefmesh:reliefmesh app ./app

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
USER reliefmesh
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
