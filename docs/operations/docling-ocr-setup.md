# Docling 与 Tesseract 配置

Docling 和 Tesseract 是可选的本地高级解析依赖，不加入基础 `requirements.txt`。Windows 支持配置将安装缓存、模型、OCR 语言包和临时文件统一放在 `D:\DevData\smartcs`。SmartCS 只使用明确配置的 Tesseract CLI 做 OCR，不自动切换其他 OCR 后端。

## 设置本地路径

在仓库根目录打开 PowerShell，设置当前终端变量并创建 D 盘目录：

```powershell
$env:PIP_CACHE_DIR = 'D:\DevData\smartcs\pip'
$env:CONDA_PKGS_DIRS = 'D:\DevData\conda-pkgs'
$env:PARSER_DATA_ROOT = 'D:\DevData\smartcs'
$env:PARSER_TEMP_DIR = 'D:\DevData\smartcs\tmp'
$env:DOCLING_ARTIFACTS_PATH = 'D:\DevData\smartcs\docling\artifacts'
$env:HF_HOME = 'D:\DevData\smartcs\huggingface'
$env:TORCH_HOME = 'D:\DevData\smartcs\torch'
$env:TESSERACT_CMD = 'D:\DevData\smartcs\tesseract-env\Library\bin\tesseract.exe'
$env:TESSDATA_PREFIX = 'D:\DevData\smartcs\tesseract-env\share\tessdata\'
$env:DOCLING_DEVICE = 'cpu'
$env:DOCLING_NUM_THREADS = '4'
$env:OMP_NUM_THREADS = '4'

New-Item -ItemType Directory -Force $env:PIP_CACHE_DIR, $env:CONDA_PKGS_DIRS, $env:PARSER_TEMP_DIR, $env:DOCLING_ARTIFACTS_PATH, $env:HF_HOME, $env:TORCH_HOME, $env:TESSDATA_PREFIX | Out-Null
```

`TESSDATA_PREFIX` 必须以斜杠结尾。所有解析器路径都必须位于 `PARSER_DATA_ROOT` 下；默认配置因此被限制在 `D:\DevData\smartcs`。只有启用高级解析时才把同样配置写入本地 `.env`，不要提交 `.env`。

不要手动修改应用进程的 `TEMP` 或 `TMP`。Uvicorn 启动和结构化基准脚本会通过同一运行时辅助函数设置并校验临时目录、模型缓存和 Tesseract 数据路径。

## 安装 Docling

先做 dry-run，确认解析结果和下载位置；执行前必须设置上面的 `PIP_CACHE_DIR`：

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pip install --dry-run -r requirements-docling.txt
```

确认后安装可选依赖：

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pip install -r requirements-docling.txt
```

`requirements-docling.txt` 只增加 Docling PDF、本地模型和 TableFormer 所需的 headless OpenCV，不选择其他 OCR 后端。文件锁定当前 Windows CPU 环境验证过的 `torch==2.12.1` 与 `torchvision==0.27.1`；修改版本前必须重新在 D 盘 dry-run 并运行完整回归。

## 预下载本地模型

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\Scripts\docling-tools.exe' models download layout tableformer --output-dir $env:DOCLING_ARTIFACTS_PATH
```

只有后续解析能力明确需要时才使用 `--all`。请求处理期间不应临时下载模型。

## 安装并验证 Tesseract

使用独立的 D 盘 conda 环境。`libcurl` 必须显式安装，因为 Windows Tesseract 依赖 `libcurl.dll`：

```powershell
& 'D:\2026.07.09\conda\Scripts\conda.exe' create `
    --override-channels -c conda-forge `
    -p 'D:\DevData\smartcs\tesseract-env' `
    'tesseract=5.5.2' libcurl -y
```

验证可执行文件，并要求中文简体和英文语言包同时存在：

```powershell
& $env:TESSERACT_CMD --version
$languages = & $env:TESSERACT_CMD --tessdata-dir $env:TESSDATA_PREFIX --list-langs
$missing = @('eng', 'chi_sim') | Where-Object { $_ -notin $languages }
if ($missing) { throw "Missing Tesseract languages: $($missing -join ', ')" }
```

不要依赖 C 盘安装或机器级 `PATH`。

## 已验证运行环境

2026-07-18 在 Windows CPU 环境验证：

- Python 3.12.13
- docling-slim 2.113.0、docling-core 2.87.1、docling-ibm-models 3.13.3
- opencv-python-headless 4.13.0.92
- torch 2.12.1、torchvision 0.27.1
- Tesseract 5.5.2，包含 `chi_sim` 与 `eng`

验证配置为 CPU、4 线程、整页 Tesseract CLI OCR，layout/TableFormer 模型位于 `D:\DevData\smartcs\docling\artifacts`，Python 临时目录位于 `D:\DevData\smartcs\tmp`。路径、可执行文件、语言包或模型不符合要求时，系统返回受控的运行时不可用结果。

## 首次解析前检查缓存

```powershell
@($env:PIP_CACHE_DIR, $env:PARSER_DATA_ROOT, $env:PARSER_TEMP_DIR, $env:DOCLING_ARTIFACTS_PATH, $env:HF_HOME, $env:TORCH_HOME, $env:TESSDATA_PREFIX) |
    ForEach-Object { Get-Item $_ | Select-Object FullName }

& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -c "from app.core.parsing.runtime import configure_parser_runtime; configure_parser_runtime(); import os,tempfile; print(tempfile.gettempdir(), os.environ['TEMP'], os.environ['TMP'], sep='\n')"

Get-ChildItem -Force "$env:LOCALAPPDATA\pip\Cache", "$env:USERPROFILE\.cache\huggingface", "$env:USERPROFILE\.cache\docling" -ErrorAction SilentlyContinue |
    Select-Object FullName

Get-ChildItem -File -Force -Recurse 'C:\Windows\Temp', "$env:LOCALAPPDATA\Temp" -ErrorAction SilentlyContinue |
    Where-Object { $_.Length -ge 10MB -and $_.Name -match '(?i)docling|pip|torch|huggingface|tesseract' } |
    Select-Object FullName, Length, LastWriteTime
```

如发现新产生的解析缓存或大型模型文件写入 C 盘，先停止解析并修正环境变量或目标路径。
