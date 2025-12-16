# 打包

```bash
pyinstaller --onefile --name main --add-data "ffmpeg.exe;." --hidden-import=multiprocessing --hidden-import=PIL --hidden-import=cv2 --hidden-import=image --hidden-import=video --hidden-import=utils main.py
```