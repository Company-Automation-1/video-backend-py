import os
import random
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from PIL import Image
import numpy as np
from tqdm import tqdm
from utils import ensure_dir


def perturb_blocks(
    image,
    block_size=3,
    replace_prob=0.2,
    replace_pixel_ratio=0.2,
    visual_debug=False,
):
    """
    对图像进行微扰动处理，肉眼几乎不可见但能干扰AI识别

    参数:
        image: 输入图像数据（PIL Image对象）
        block_size: 块的大小(默认3x3像素)
        replace_prob: 每个块被随机替换的概率(0-1之间，默认0.2即20%)
        replace_pixel_ratio: 被选中块内有多少像素被随机替换(0-1之间，默认0.2即20%)
        visual_debug: 是否启用可视化调试模式

    返回:
        处理后的图像数据（PIL Image对象）
    """
    img = image.convert("RGB")
    width, height = img.size
    pixels = np.array(img)
    perturbed_pixels = pixels.copy()

    # 计算完整块的数量（只处理完整块，非完整块自动跳过）
    num_blocks_y = height // block_size
    num_blocks_x = width // block_size

    # 块级别的随机选择（numpy操作，释放GIL）
    block_mask = np.random.random((num_blocks_y, num_blocks_x)) < replace_prob

    # 遍历所有完整块，但只处理被选中的块
    for by in range(num_blocks_y):
        for bx in range(num_blocks_x):
            if not block_mask[by, bx]:
                continue

            # 计算块的位置
            y = by * block_size
            x = bx * block_size

            # 获取块（需要copy才能正确修改）
            block = perturbed_pixels[y : y + block_size, x : x + block_size, :].copy()

            # 计算需要扰动的像素数量
            total_pixels = block_size * block_size
            num_to_perturb = max(1, int(total_pixels * replace_pixel_ratio))

            # 随机选择像素位置
            positions = [(i, j) for i in range(block_size) for j in range(block_size)]
            perturb_positions = random.sample(positions, num_to_perturb)
            for i, j in perturb_positions:
                r, g, b = block[i, j]
                dr = random.randint(-20, 20)
                dg = random.randint(-20, 20)
                db = random.randint(-20, 20)
                block[i, j, 0] = np.uint8(max(0, min(255, int(r) + dr)))
                block[i, j, 1] = np.uint8(max(0, min(255, int(g) + dg)))
                block[i, j, 2] = np.uint8(max(0, min(255, int(b) + db)))

            # 可视化调试
            if visual_debug:
                block[:, 0, :] = [255, 0, 0]
                block[:, -1, :] = [255, 0, 0]
                block[0, :, :] = [255, 0, 0]
                block[-1, :, :] = [255, 0, 0]

            # 写回块
            perturbed_pixels[y : y + block_size, x : x + block_size, :] = block

    return Image.fromarray(perturbed_pixels)


def process_image(
    image_path,
    output_path,
    block_size=3,
    replace_prob=0.2,
    replace_pixel_ratio=0.2,
    visual_debug=False,
):
    """
    处理单个图片并保存到指定路径

    参数:
        image_path: 输入图像路径
        output_path: 输出目录路径
        block_size: 块的大小(默认3x3像素)
        replace_prob: 每个块被随机替换的概率(0-1之间，默认0.2即20%)
        replace_pixel_ratio: 被选中块内有多少像素被随机替换(0-1之间，默认0.2即20%)
        visual_debug: 是否启用可视化调试模式
    """
    ensure_dir(output_path)
    filename = os.path.basename(image_path)
    output_path = os.path.join(output_path, filename)

    img = Image.open(image_path)
    perturbed_img = perturb_blocks(
        img,
        block_size,
        replace_prob,
        replace_pixel_ratio,
        visual_debug,
    )
    perturbed_img.save(output_path)


def _process_single_file_worker(args):
    """
    子进程工作函数：只处理图片

    参数:
        args: (image_file, input_folder, output_folder, block_size,
               replace_prob, replace_pixel_ratio, visual_debug)

    返回:
        (success: bool, image_file: str, error: str or None)
    """
    (
        image_file,
        input_folder,
        output_folder,
        block_size,
        replace_prob,
        replace_pixel_ratio,
        visual_debug,
    ) = args

    try:
        input_path = os.path.join(input_folder, image_file)
        output_path = os.path.join(output_folder, image_file)

        img = Image.open(input_path)
        perturbed_img = perturb_blocks(
            img, block_size, replace_prob, replace_pixel_ratio, visual_debug
        )
        perturbed_img.save(output_path)

        return (True, image_file, None)
    except Exception as e:
        return (False, image_file, str(e))


def process_folder(
    input_folder,
    output_folder,
    block_size=3,
    replace_prob=0.2,
    replace_pixel_ratio=0.2,
    visual_debug=False,
    progress_callback=None,
    max_workers=4,
):
    """
    批量处理文件夹中的所有图片

    参数:
        input_folder: 输入图像文件夹路径
        output_folder: 输出图像文件夹路径
        block_size: 块的大小(默认3x3像素)
        replace_prob: 每个块被随机替换的概率(0-1之间，默认0.2即20%)
        replace_pixel_ratio: 被选中块内有多少像素被随机替换(0-1之间，默认0.2即20%)
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
                    block_size,
                    replace_prob,
                    replace_pixel_ratio,
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
    # ========== 测试配置（请填入你的测试路径）==========
    # TEST_IMAGE_PATH = r"public\input\640.jpg"
    TEST_IMAGE_PATH = r"C:\Users\hly\Desktop\RePkg\1bae2d76f5451352f72106c518a818c2.jpg"
    TEST_INPUT_DIR = r"test\test"
    TEST_OUTPUT_DIR = r"test\test_output"
    # ==================================================

    # print("=" * 50)
    # print("image_perturb.py 单测")
    # print("=" * 50)

    # # 测试1: process_image
    # print("\n[测试1] process_image...")
    # process_image(
    #     TEST_IMAGE_PATH,
    #     TEST_OUTPUT_DIR,
    #     block_size=5,
    #     replace_prob=0.3,
    #     replace_pixel_ratio=0.5,
    #     visual_debug=False,
    # )
    # print(f"✓ 输出: {os.path.join(TEST_OUTPUT_DIR, os.path.basename(TEST_IMAGE_PATH))}")

    # 测试2: process_folder
    print("\n[测试2] process_folder...")
    folder_output_dir = os.path.join(TEST_OUTPUT_DIR, "folder_output")

    image_files = [
        f
        for f in os.listdir(TEST_INPUT_DIR)
        if f.endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif"))
    ]

    pbar = tqdm(total=len(image_files), desc="Processing images")

    def progress_callback(current, total, info):
        pbar.update(1)

    process_folder(
        TEST_INPUT_DIR,
        folder_output_dir,
        block_size=5,
        replace_prob=0.2,
        replace_pixel_ratio=0.2,
        visual_debug=True,
        progress_callback=progress_callback,
    )
    pbar.close()
    print(f"✓ 处理了 {len(image_files)} 张图片")

    print("\n" + "=" * 50)
    print("测试完成！")
    print("=" * 50)
