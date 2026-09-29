FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /project

COPY requirements.txt /project/requirements.txt

RUN pip install --upgrade pip

# PyTorch и torchvision обязательно ставим одной совместимой парой
# из одного и того же CPU-репозитория.
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.14.0+cpu \
    torchvision==0.29.0+cpu

# Остальные зависимости уже не должны переустанавливать torch/torchvision.
RUN pip install --no-cache-dir -r /project/requirements.txt
# RapidOCR declares opencv-python as a dependency.
# The backend uses opencv-python-headless instead, so install RapidOCR
# without dependencies to avoid two conflicting cv2 distributions.
RUN pip install --no-cache-dir --no-deps rapidocr-onnxruntime

COPY backend /project/backend

WORKDIR /project/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]