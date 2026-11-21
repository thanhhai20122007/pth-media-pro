FROM python:3.12-slim

# Cài đặt FFmpeg, Aria2 và các công cụ cần thiết
RUN apt-get update && apt-get install -y ffmpeg aria2 curl && rm -rf /var/lib/apt/lists/

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Port 7860 tiêu chuẩn cho Hugging Face Spaces hoặc Cloud Server
ENV PORT=7860
EXPOSE 7860

CMD ["sh", "-c", "python main.py --mode headless --port ${PORT:-7860}"]
