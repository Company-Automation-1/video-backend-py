import os
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from PIL import Image
import numpy as np
from utils import ensure_dir
from pathlib import Path
import time


def perturb_blocks(
    image,
    perturb_prob=0.01,
    visual_debug=False,
):
    """
    对图像进行微扰动处理，肉眼几乎不可见但能干扰AI识别

    参数:
        image: 输入图像数据（PIL Image对象）
        perturb_prob: 像素被扰动的概率(0-1之间，默认0.01即1%)
        visual_debug: 是否启用可视化调试模式

    返回:
        处理后的图像数据（PIL Image对象）
    """
    img = image.convert("RGB")
    width, height = img.size
    pixels = np.array(img, dtype=np.int16)  # 使用int16避免溢出

    # 计算总像素数和要扰动的像素数
    total_pixels = width * height
    num_to_perturb = int(total_pixels * perturb_prob)
    
    if num_to_perturb == 0:
        return Image.fromarray(pixels.astype(np.uint8))

    # 生成随机线性索引（避免创建坐标列表）
    pixel_indices = np.random.choice(total_pixels, size=num_to_perturb, replace=False)
    
    # 将图像reshape为2D数组 (height*width, 3)，每行是一个像素的RGB
    pixels_flat = pixels.reshape(-1, 3)
    
    # 批量生成随机通道索引（0=R, 1=G, 2=B）
    channels = np.random.randint(0, 3, size=num_to_perturb)
    
    # 批量生成随机扰动值（±1到±3）
    deltas = np.random.choice([-3, -2, -1, 1, 2, 3], size=num_to_perturb)
    
    # 使用高级索引一次性修改所有选中的像素
    # pixels_flat[pixel_indices, channels] 选择要修改的像素和通道
    pixels_flat[pixel_indices, channels] += deltas
    
    # 使用clip确保值在0-255范围内（向量化操作）
    pixels_flat = np.clip(pixels_flat, 0, 255)
    
    # 转换回原始形状和uint8类型
    perturbed_pixels = pixels_flat.reshape(height, width, 3).astype(np.uint8)
    
    # 可视化调试：标记被扰动的像素
    if visual_debug:
        # 将线性索引转换为坐标
        y_coords, x_coords = np.unravel_index(pixel_indices, (height, width))
        perturbed_pixels[y_coords, x_coords] = [255, 0, 0]  # 红色标记

    return Image.fromarray(perturbed_pixels)


def process_image(
    image_path,
    output_path,
    perturb_prob=0.01,
    visual_debug=False,
):
    """
    处理单个图片并保存到指定路径

    参数:
        image_path: 输入图像路径
        output_path: 输出目录路径
        perturb_prob: 像素被扰动的概率(0-1之间，默认0.01即1%)
        visual_debug: 是否启用可视化调试模式
    """
    ensure_dir(output_path)
    filename = os.path.basename(image_path)
    output_path = os.path.join(output_path, filename)

    img = Image.open(image_path)
    perturbed_img = perturb_blocks(
        img,
        perturb_prob,
        visual_debug,
    )
    perturbed_img.save(output_path)


def _process_single_file_worker(args):
    """
    子进程工作函数：只处理图片

    参数:
        args: (image_file, input_folder, output_folder, perturb_prob, visual_debug)

    返回:
        (success: bool, image_file: str, error: str or None)
    """
    (
        image_file,
        input_folder,
        output_folder,
        perturb_prob,
        visual_debug,
    ) = args

    try:
        input_path = os.path.join(input_folder, image_file)
        output_path = os.path.join(output_folder, image_file)

        img = Image.open(input_path)
        perturbed_img = perturb_blocks(
            img, perturb_prob, visual_debug
        )
        perturbed_img.save(output_path)

        return (True, image_file, None)
    except Exception as e:
        return (False, image_file, str(e))


def process_folder(
    input_folder,
    output_folder,
    perturb_prob=0.01,
    visual_debug=False,
    progress_callback=None,
    max_workers=4,
):
    """
    批量处理文件夹中的所有图片

    参数:
        input_folder: 输入图像文件夹路径
        output_folder: 输出图像文件夹路径
        perturb_prob: 像素被扰动的概率(0-1之间，默认0.01即1%)
        visual_debug: 是否启用可视化调试模式
        progress_callback: 进度回调函数，接收参数 (current: int, total: int, info: str) -> None
        max_workers: 最大工作进程数，默认使用CPU核心数
    """
    ensure_dir(output_folder)

    image_files = [
        f
        for f in os.listdir(input_folder)
        if f.endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif"))
    ]
    total = len(image_files)

    if total == 0:
        return

    if max_workers is None:
        max_workers = max(1, multiprocessing.cpu_count() - 2)

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(
                _process_single_file_worker,
                (
                    image_file,
                    input_folder,
                    output_folder,
                    perturb_prob,
                    visual_debug,
                ),
            ): image_file
            for image_file in image_files
        }

        completed_count = 0
        for future in as_completed(future_to_file):
            future.result()  # 等待任务完成并捕获异常
            completed_count += 1
            if progress_callback:
                progress_callback(min(completed_count, total), total, "处理帧图像")


if __name__ == "__main__":
    BASE = Path(__file__).parent
    # ========== 测试配置（请填入你的测试路径）==========
    TEST_IMAGE_PATH = BASE / "public" / "1.jpg"
    TEST_OUTPUT_DIR = BASE / "public" / "output"
    # ==================================================

    print("=" * 50)
    print("image.py 测试")
    print("=" * 50)

    # 测试1: process_image
    print("\n[测试1] process_image...")
    start_time = time.time()
    process_image(
        TEST_IMAGE_PATH,
        TEST_OUTPUT_DIR,
        perturb_prob=0.01,
        visual_debug=True,
    )
    end_time = time.time()
    print(f"✓ 输出: {os.path.join(TEST_OUTPUT_DIR, os.path.basename(TEST_IMAGE_PATH))}")
    print(f"✓ 耗时: {end_time - start_time} 秒")