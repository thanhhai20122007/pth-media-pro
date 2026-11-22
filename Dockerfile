FROM python:3.12-slim

# Cài đặt Node.js, Deno (giải mã bot challenge của YouTube), FFmpeg, Aria2, curl và unzip
RUN apt-get update && apt-get install -y nodejs ffmpeg aria2 curl unzip && \
    (which node || ln -sf /usr/bin/nodejs /usr/bin/node) && \
    (curl -fsSL https://deno.land/install.sh | sh && cp /root/.deno/bin/deno /usr/local/bin/deno && chmod +x /usr/local/bin/deno || true) && \
    rm -rf /var/lib/apt/lists/

WORKDIR /app

# Luôn cập nhật pip và yt-dlp lên bản mới nhất
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip setuptools wheel && \
    pip install --no-cache-dir -U -r requirements.txt && \
    pip install --no-cache-dir -U yt-dlp

COPY . .

# Ghi lại dấu ấn bản build độc nhất mỗi lần Render build
RUN date +%s > /app/build_id.txt

# Port 7860 tiêu chuẩn cho Hugging Face Spaces hoặc Cloud Server
ENV PORT=7860
EXPOSE 7860

CMD ["sh", "-c", "python main.py --mode headless --port ${PORT:-7860}"]
