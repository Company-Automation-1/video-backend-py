# 打包

```bash
# 相对路径
pyinstaller --onefile --name main --add-data "ffmpeg.exe;." --hidden-import=multiprocessing --hidden-import=PIL --hidden-import=cv2 --hidden-import=image --hidden-import=video --hidden-import=utils main.py

# 绝对路径
python -m PyInstaller --onefile --name main --add-data 'ffmpeg.exe;.' --hidden-import=multiprocessing --hidden-import=PIL --hidden-import=cv2 --hidden-import=image --hidden-import=video --hidden-import=utils "E:\WWW\develop\company_1\video\python\main.py"
```

# 部署

## 使用 NSSM 部署为 Windows 服务

### 1. 下载 NSSM
从 [NSSM 官网](https://nssm.cc/download) 下载并解压，将 `nssm.exe` 放到系统 PATH 或项目目录。

### 2. 安装服务

```bash
# 以管理员身份运行 PowerShell 或 CMD

# 设置变量（根据实际路径修改）
$exePath = "E:\WWW\develop\company_1\video\python\dist\main.exe"
$serviceName = "VideoProcessService"

# 安装服务
nssm install $serviceName $exePath

# 设置工作目录（重要：程序需要在此目录创建 temp 文件夹）
nssm set $serviceName AppDirectory "E:\WWW\develop\company_1\video\python\dist"

# 设置服务描述
nssm set $serviceName Description "视频/图片处理服务 - FastAPI"

# 设置启动类型为自动（可选）
nssm set $serviceName Start SERVICE_AUTO_START

# 设置日志输出（可选）
nssm set $serviceName AppStdout "E:\WWW\develop\company_1\video\python\dist\service_stdout.log"
nssm set $serviceName AppStderr "E:\WWW\develop\company_1\video\python\dist\service_stderr.log"

# 设置日志轮转（可选，防止日志文件过大）
nssm set $serviceName AppRotateFiles 1
nssm set $serviceName AppRotateOnline 1
nssm set $serviceName AppRotateSeconds 86400  # 每天轮转
nssm set $serviceName AppRotateBytes 10485760  # 10MB

# 启动服务
nssm start $serviceName
```

### 3. 服务管理命令

```bash
# 启动服务
nssm start VideoProcessService
# 或使用 Windows 服务管理
net start VideoProcessService

# 停止服务
nssm stop VideoProcessService
# 或
net stop VideoProcessService

# 重启服务
nssm restart VideoProcessService

# 查看服务状态
nssm status VideoProcessService

# 查看服务配置
nssm get VideoProcessService AppDirectory
nssm get VideoProcessService AppParameters

# 编辑服务配置（图形界面）
nssm edit VideoProcessService

# 删除服务
nssm remove VideoProcessService confirm
```

### 4. 注意事项

- **工作目录**：必须设置为 exe 所在目录，因为程序会在该目录创建 `temp` 文件夹
- **端口占用**：确保 8000 端口未被占用，或修改 `main.py` 中的端口号
- **防火墙**：如需外部访问，需在防火墙中开放 8000 端口
- **权限**：安装服务需要管理员权限
- **ffmpeg.exe**：已打包进 exe，无需单独配置

### 5. 验证服务

```bash
# 检查服务是否运行
Get-Service VideoProcessService

# 测试 API（服务启动后）
curl http://localhost:8000/
curl http://localhost:8000/docs  # API 文档
```