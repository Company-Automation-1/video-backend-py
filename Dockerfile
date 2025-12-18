# 使用 Python 3.11 作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（安装 curl 用于健康检查）
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.cicd.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.cicd.txt

# 复制应用
COPY . .

# 设置 FFmpeg 执行权限
RUN chmod +x ./ffmpeg

# 创建临时目录
RUN mkdir -p /app/temp

# 暴露端口
EXPOSE 6869

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 启动应用
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "6869"]
