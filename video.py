import os
import cv2
import subprocess
import shutil
from typing import Optional, Callable
from utils import get_ffmpeg_path, ensure_dir
from tqdm import tqdm
from image import process_folder
from pathlib import Path

FFMPEG_PATH = get_ffmpeg_path()


def video_to_frames(
    video_path,
    output_folder,
    frame_prefix="frame_",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
):
    """
    将视频分解为帧序列（使用FFmpeg，性能更优）

    参数:
        video_path: 输入视频路径
        output_folder: 输出帧序列保存文件夹
        frame_prefix: 帧文件名前缀
        progress_callback: 进度回调函数，接收参数 (current: int, total: int, info: str) -> None
    """
    ensure_dir(output_folder)

    # 先用cv2快速获取视频信息
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"无法打开视频文件: {video_path}")
        return None, None

    # 获取视频信息
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    print(f"视频信息: {os.path.basename(video_path)}")
    print(f"帧率: {fps:.2f} FPS, 总帧数: {total_frames}")

    # 使用FFmpeg批量提取所有帧（性能更优）
    print("使用FFmpeg提取帧序列...")
    output_pattern = os.path.join(output_folder, f"{frame_prefix}%06d.jpg")

    cmd = [
        FFMPEG_PATH,
        "-i",
        video_path,
        "-q:v",
        "2",  # JPEG质量（2=高质量）
        "-y",  # 覆盖输出文件
        output_pattern,
    ]

    try:
        # 实时解析FFmpeg输出获取进度
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1
        )

        # 解析FFmpeg stderr输出获取进度
        for line in process.stderr:
            if "frame=" in line:
                try:
                    # 提取帧号: frame=  123
                    frame_str = line.split("frame=")[1].split()[0]
                    current_frame = int(frame_str)
                    if progress_callback:
                        progress_callback(
                            min(current_frame, total_frames),
                            total_frames,
                            "分解视频为帧",
                        )
                except (ValueError, IndexError):
                    pass

        process.wait()

        if process.returncode != 0:
            print("FFmpeg提取失败")
            return None, None

        # 统计实际提取的帧数
        frame_files = [
            f
            for f in os.listdir(output_folder)
            if f.startswith(frame_prefix) and f.endswith(".jpg")
        ]
        actual_frame_count = len(frame_files)

        print(f"视频分解完成! 共提取 {actual_frame_count} 帧图像")
        return fps, total_frames

    except Exception as e:
        print(f"使用FFmpeg提取帧时出错: {e}")
        return None, None


def frames_to_video(frames_folder, output_video, fps=30, frame_prefix="frame_"):
    """
    使用ffmpeg将帧序列合成为视频 (H.264编码)
    """
    # 获取所有帧文件
    frame_files = [
        f
        for f in os.listdir(frames_folder)
        if f.startswith(frame_prefix) and f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]
    frame_files.sort()
    if not frame_files:
        print(f"在 {frames_folder} 中未找到帧文件")
        return False

    # 获取第一帧的尺寸
    first_frame = cv2.imread(os.path.join(frames_folder, frame_files[0]))
    if first_frame is None:
        print("无法读取第一帧")
        return False
    height, width, _ = first_frame.shape

    # 构建ffmpeg命令
    cmd = [
        FFMPEG_PATH,
        "-y",  # 覆盖输出文件
        "-r",
        str(fps),  # 设置输入帧率
        "-f",
        "image2",  # 输入格式为图片序列
        "-s",
        f"{width}x{height}",  # 指定图像尺寸
        "-i",
        os.path.join(frames_folder, f"{frame_prefix}%06d.jpg"),  # 输入图片路径
        "-vcodec",
        "libx264",  # 使用libx264编码器
        "-b:v",
        "1800k",  # 设置目标视频码率 (这里设为1.8Mbps，接近原始码率)
        "-pix_fmt",
        "yuv420p",  # 兼容性最好的像素格式
        "-preset",
        "medium",  # 编码速度与压缩率的平衡
        "-profile:v",
        "main",  # 指定H.264 profile
        "-level",
        "4.1",  # 指定H.264 level
        output_video,
    ]

    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if result.returncode == 0:
            print(f"视频合成完成! 保存到 {os.path.basename(output_video)}")
            return True
        else:
            print(f"视频合成失败: {result.stderr}")
            return False
    except Exception as e:
        print(f"执行ffmpeg命令时出错: {e}")
        return False


def extract_video_audio(video_path, audio_output_path):
    """
    提取视频音频

    参数:
        video_path: 输入视频路径
        audio_output_path: 输出音频路径
    """
    try:
        # 提取音频
        print("提取视频音频...")
        extract_cmd = [
            FFMPEG_PATH,
            "-i",
            video_path,
            "-vn",
            "-acodec",
            "copy",
            audio_output_path,
            "-y",
        ]
        result = subprocess.run(
            extract_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        has_audio = result.returncode == 0

        if has_audio:
            print("音频提取成功")
        else:
            print("视频没有音频或提取失败")

        return has_audio
    except (subprocess.SubprocessError, FileNotFoundError):
        print("未检测到FFmpeg，将生成无声视频")
        return False
    except Exception as e:
        print(f"提取音频时出错: {e}")
        return False


def merge_video_audio(video_path, audio_path, output_path):
    """
    合并视频和音频

    参数:
        video_path: 视频文件路径
        audio_path: 音频文件路径
        output_path: 输出文件路径
    """
    try:
        merge_cmd = [
            FFMPEG_PATH,
            "-i",
            video_path,
            "-i",
            audio_path,
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-shortest",
            # 🔥🔥🔥 【核心元数据伪装】🔥🔥🔥
            # 1. 技术伪装
            "-metadata",
            "encoder=Lavf58.20.100",  # 伪装成旧版编码器
            "-metadata",
            "compatible_brands=isom/iso2/avc1/mp41",  # 伪装成H.264标准
            # 2. 清空所有描述性元数据
            "-metadata",
            "title=",  # 清空标题
            "-metadata",
            "artist=",  # 清空作者
            "-metadata",
            "album=",  # 清空专辑
            "-metadata",
            "date=",  # 清空日期
            "-metadata",
            "genre=",  # 清空流派
            "-metadata",
            "comment=",  # 清空注释
            "-metadata",
            "description=",  # 清空描述
            "-metadata",
            "copyright=",  # 清空版权
            "-metadata",
            "encoded_by=",  # 清空编码者
            "-metadata",
            "creation_time=",  # 清空创建时间 (FFmpeg会自动写入新的)
            "-y",
            output_path,
        ]
        subprocess.run(
            merge_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
        )
        print(f"音频合并成功: {os.path.basename(output_path)}")
        return True
    except Exception as e:
        print(f"合并音频时出错: {e}")
        return False


def main(
    input_video_path,
    output_video_path,
    perturb_prob=0.01,
    visual_debug=False,
    progress_callback=None,
    max_workers=None,
):
    """
    视频处理流程编排

    参数:
        input_video_path: 输入视频路径
        output_video_path: 输出视频路径
        perturb_prob: 像素被扰动的概率(0-1之间，默认0.01即1%)
        visual_debug: 是否启用可视化调试模式
        progress_callback: 进度回调函数，接收参数 (current: int, total: int, info: str) -> None
        max_workers: 最大工作进程数，默认使用CPU核心数

    返回:
        dict: 处理结果字典，包含:
            - success: bool, 是否成功
            - output_path: str, 输出文件路径
            - metadata: dict, 元数据 (fps, total_frames, has_audio)
            - error: str, 错误信息（如果失败）
    """
    output_dir = os.path.dirname(output_video_path)
    ensure_dir(output_dir)
    # 使用输出文件名（不含扩展名）创建独立的临时目录，避免多任务冲突
    output_basename = os.path.splitext(os.path.basename(output_video_path))[0]
    catch_dir = os.path.join(output_dir, f"catch_{output_basename}")
    frames_dir = os.path.join(catch_dir, "frames")  # 原始帧序列
    processed_frames_dir = os.path.join(catch_dir, "processed_frames")  # 处理后的帧序列
    audio_path = os.path.join(catch_dir, "audio.aac")  # 音频
    temp_video = os.path.join(catch_dir, "temp_video.mp4")  # 临时视频

    result = {
        "success": False,
        "output_path": output_video_path,
        "metadata": {},
        "error": None,
    }

    try:
        fps, total_frames = video_to_frames(
            input_video_path, frames_dir, progress_callback=progress_callback
        )  # 将视频分解为帧序列
        if fps is None or total_frames is None:
            raise Exception("视频分解为帧序列失败")

        process_folder(
            frames_dir,
            processed_frames_dir,
            perturb_prob=perturb_prob,
            visual_debug=visual_debug,
            progress_callback=progress_callback,
            max_workers=max_workers,
        )
        has_audio = extract_video_audio(input_video_path, audio_path)  # 提取音频

        if not frames_to_video(processed_frames_dir, temp_video, fps=fps):  # 将帧序列合成为视频
            raise Exception("帧序列合成视频失败")

        if has_audio:
            if not merge_video_audio(temp_video, audio_path, output_video_path):  # 合并视频和音频
                raise Exception("合并视频和音频失败")
        else:
            shutil.move(temp_video, output_video_path)  # 移动临时视频到输出视频路径

        shutil.rmtree(catch_dir)  # 删除临时文件夹

        result["success"] = True
        result["metadata"] = {
            "fps": fps,
            "total_frames": total_frames,
            "has_audio": has_audio,
        }
        return result

    except Exception as e:
        result["error"] = str(e)
        if os.path.exists(catch_dir):
            shutil.rmtree(catch_dir)
        return result


if __name__ == "__main__":
    BASE = Path(__file__).parent
    input_video_path = BASE / "public" / "3.mp4"
    output_video_path = BASE / "public" / "output" / "3.mp4"

    class ProgressCallback:
        def __init__(self):
            self.pbar = None

        def __call__(self, current, total, info):
            if self.pbar is None:
                self.pbar = tqdm(total=total, desc=info)
            self.pbar.n = current
            self.pbar.refresh()
            if current >= total:
                self.pbar.close()
                self.pbar = None

    progress_callback = ProgressCallback()
    result = main(
        input_video_path,
        output_video_path,
        perturb_prob=0.1,
        visual_debug=True,
        progress_callback=progress_callback,
        max_workers=None,
    )
    if result["success"]:
        print(f"✓ 视频处理成功: {result['output_path']}")
        print(f"  元数据: {result['metadata']}")
    else:
        print(f"✗ 视频处理失败: {result.get('error', '未知错误')}")
