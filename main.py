import os
import uuid
import asyncio
import json
from contextlib import asynccontextmanager
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image
import io
from image import perturb_blocks
from video import main as process_video
from utils import ensure_dir
import multiprocessing

########################################################
# 配置
# 获取CPU核心数
CPU_COUNT = multiprocessing.cpu_count()

# 图片处理：可以较多并发，因为处理快且资源占用小
# 建议：CPU核心数的 1-1.5 倍（因为图片处理快，可以快速释放资源）
image_max_workers = max(4, min(CPU_COUNT, 12))

# 视频处理：需要严格控制，因为每个视频内部还会启动多进程
# 建议：根据CPU核心数动态调整
# - 4核以下：1个
# - 4-8核：2个
# - 8核以上：2-3个
if CPU_COUNT <= 4:
    video_max_workers = 1
elif CPU_COUNT <= 8:
    video_max_workers = 2
else:
    video_max_workers = min(3, CPU_COUNT // 4)  # 最多3个，或CPU核心数的1/4
########################################################

# 线程池用于执行CPU密集型任务
IMAGE_EXECUTOR = ThreadPoolExecutor(
    max_workers=image_max_workers, thread_name_prefix="image_"
)
VIDEO_EXECUTOR = ThreadPoolExecutor(
    max_workers=video_max_workers, thread_name_prefix="video_"
)

# 并发控制：限制同时处理的请求数
# 图片处理允许更多并发（CPU密集型但速度快）
IMAGE_SEMAPHORE = asyncio.Semaphore(image_max_workers)
# 视频处理限制更严格（CPU密集型且耗时长）
VIDEO_SEMAPHORE = asyncio.Semaphore(video_max_workers)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    yield
    # 关闭时清理资源
    IMAGE_EXECUTOR.shutdown(wait=True)
    VIDEO_EXECUTOR.shutdown(wait=True)


app = FastAPI(lifespan=lifespan)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境建议指定具体域名
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有请求头
)

# 临时文件目录
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
ensure_dir(TEMP_DIR)

# 任务进度存储
task_progress = defaultdict(dict)


def _process_image_sync(
    contents: bytes,
    filename: str,
    perturb_prob: float,
    visual_debug: bool,
):
    """同步处理图片（在线程池中执行）"""
    img = Image.open(io.BytesIO(contents))
    processed_img = perturb_blocks(
        img,
        perturb_prob=perturb_prob,
        visual_debug=visual_debug,
    )

    output = io.BytesIO()
    if filename and filename.lower().endswith((".jpg", ".jpeg")):
        processed_img.save(output, format="JPEG", quality=90)
        media_type = "image/jpeg"
    else:
        processed_img.save(output, format="PNG")
        media_type = "image/png"

    output.seek(0)
    return output.read(), media_type


@app.post("/process_image")
async def process_image_api(
    file: UploadFile = File(...),
    perturb_prob: float = Form(0.01),
    visual_debug: bool = Form(False),
):
    """
    处理图片接口

    参数:
        file: 上传的图片文件
        perturb_prob: 像素被扰动的概率(0-1之间，默认0.01即1%)
        visual_debug: 是否启用可视化调试模式(默认False)
    """
    async with IMAGE_SEMAPHORE:  # 限制并发数
        try:
            # 读取上传的图片
            contents = await file.read()

            # 在线程池中执行CPU密集型任务
            loop = asyncio.get_event_loop()
            result_data, media_type = await loop.run_in_executor(
                IMAGE_EXECUTOR,
                _process_image_sync,
                contents,
                file.filename or "image",
                perturb_prob,
                visual_debug,
            )

            # 返回处理后的图片
            return StreamingResponse(
                io.BytesIO(result_data),
                media_type=media_type,
                headers={
                    "Content-Disposition": f"attachment; filename=processed_{file.filename}"
                },
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"处理图片时出错: {str(e)}")


def _process_video_sync(
    input_path: str,
    output_path: str,
    perturb_prob: float,
    visual_debug: bool,
    task_id: str,
):
    """同步处理视频（在线程池中执行）"""

    def progress_callback(current, total, info):
        if task_id in task_progress:
            task_progress[task_id].update(
                {
                    "current": current,
                    "total": total,
                    "info": info,
                    "status": "processing",
                    "progress": int((current / total) * 100) if total > 0 else 0,
                }
            )

    try:
        result = process_video(
            input_video_path=input_path,
            output_video_path=output_path,
            perturb_prob=perturb_prob,
            visual_debug=visual_debug,
            progress_callback=progress_callback,
            max_workers=None,
        )

        if not result["success"]:
            error_msg = result.get("error", "视频处理失败")
            raise Exception(error_msg)

        if task_id in task_progress:
            task_progress[task_id]["status"] = "completed"
            task_progress[task_id]["progress"] = 100
            task_progress[task_id]["metadata"] = result.get("metadata", {})

    except Exception as e:
        if task_id in task_progress:
            task_progress[task_id]["status"] = "error"
            task_progress[task_id]["error"] = str(e)
        raise
    finally:
        # 处理完成后清理输入文件（输出文件保留供下载）
        if input_path and os.path.exists(input_path):
            try:
                os.remove(input_path)
            except Exception:
                pass


async def _process_video_async(
    input_path: str,
    output_path: str,
    perturb_prob: float,
    visual_debug: bool,
    task_id: str,
):
    """异步处理视频（在后台执行）"""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            VIDEO_EXECUTOR,
            _process_video_sync,
            input_path,
            output_path,
            perturb_prob,
            visual_debug,
            task_id,
        )
    except Exception as e:
        if task_id in task_progress:
            task_progress[task_id]["status"] = "error"
            task_progress[task_id]["error"] = str(e)


@app.post("/process_video")
async def process_video_api(
    file: UploadFile = File(...),
    perturb_prob: float = Form(0.01),
    visual_debug: bool = Form(False),
):
    """处理视频接口，返回任务ID"""
    async with VIDEO_SEMAPHORE:
        input_path = None
        output_path = None
        task_id = str(uuid.uuid4())

        try:
            unique_id = str(uuid.uuid4())
            file_ext = os.path.splitext(file.filename or "video")[1]
            input_path = os.path.join(TEMP_DIR, f"input_{unique_id}{file_ext}")
            output_path = os.path.join(TEMP_DIR, f"output_{unique_id}.mp4")

            task_progress[task_id] = {
                "current": 0,
                "total": 100,
                "info": "准备中...",
                "status": "pending",
                "progress": 0,
                "output_path": output_path,
                "filename": file.filename,
            }

            with open(input_path, "wb") as f:
                content = await file.read()
                f.write(content)

            task_progress[task_id]["status"] = "processing"
            task_progress[task_id]["info"] = "开始处理..."

            asyncio.create_task(
                _process_video_async(
                    input_path,
                    output_path,
                    perturb_prob,
                    visual_debug,
                    task_id,
                )
            )

            return {"task_id": task_id}
        except HTTPException:
            raise
        except Exception as e:
            if input_path and os.path.exists(input_path):
                try:
                    os.remove(input_path)
                except Exception:
                    pass
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            if task_id in task_progress:
                task_progress[task_id]["status"] = "error"
                task_progress[task_id]["error"] = str(e)
            raise HTTPException(status_code=500, detail=f"处理视频时出错: {str(e)}")


@app.get("/video_progress/{task_id}")
async def video_progress(task_id: str):
    """SSE推送视频处理进度"""

    async def event_generator():
        while True:
            if task_id not in task_progress:
                yield f"data: {json.dumps({'error': '任务不存在'})}\n\n"
                break

            progress_data = task_progress[task_id].copy()
            yield f"data: {json.dumps(progress_data)}\n\n"

            if progress_data.get("status") in ["completed", "error"]:
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/video_result/{task_id}")
async def video_result(task_id: str):
    """获取处理完成的视频"""
    if task_id not in task_progress:
        raise HTTPException(status_code=404, detail="任务不存在")

    progress = task_progress[task_id]
    if progress["status"] != "completed":
        raise HTTPException(status_code=400, detail="视频处理未完成")

    output_path = progress.get("output_path")
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="输出文件不存在")

    filename = progress.get("filename", "processed_video.mp4")
    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"processed_{filename}",
    )


@app.get("/")
async def root():
    """根路径，返回API信息"""
    return {
        "message": "视频/图片处理API",
        "endpoints": {
            "/process_image": "POST - 处理图片",
            "/process_video": "POST - 处理视频",
            "/video_progress/{task_id}": "GET - SSE进度推送",
            "/video_result/{task_id}": "GET - 获取处理结果",
            "/docs": "GET - API文档",
            "/health": "GET - 健康检查",
        },
    }


@app.get("/health")
async def health():
    """健康检查接口"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    # Windows 上 PyInstaller 打包后，确保只在主进程中启动服务器
    multiprocessing.freeze_support()
    uvicorn.run(app, host="0.0.0.0", port=6869)
