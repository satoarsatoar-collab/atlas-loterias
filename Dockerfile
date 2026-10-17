FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1 PORT=8080 ATLAS_CADA_HORAS=6 ATLAS_DESCARGA=si
EXPOSE 8080
HEALTHCHECK --interval=5m --timeout=10s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/salud')"
CMD ["python", "-m", "atlas.servidor"]
