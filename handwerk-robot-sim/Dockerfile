FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libegl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY . .

# Download H1 mesh assets from mujoco_menagerie (not committed to git)
RUN bash setup_model.sh

EXPOSE 7860

CMD ["python3", "sim/ws_server.py", \
     "--model", "h1_hand", \
     "--headless", \
     "--host", "0.0.0.0", \
     "--port", "7860"]
