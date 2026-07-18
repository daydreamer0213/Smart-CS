# Docling and Tesseract Setup

Docling and Tesseract are optional local dependencies. Keep package caches,
model artifacts, and OCR language data on `D:`. Do not add this optional
dependency to `requirements.txt`.

## Set the local paths

Run these commands in PowerShell from the repository root. They only set
environment variables for the current shell.

```powershell
$env:PIP_CACHE_DIR = 'D:\DevData\smartcs\pip'
$env:DOCLING_ARTIFACTS_PATH = 'D:\DevData\smartcs\docling\artifacts'
$env:HF_HOME = 'D:\DevData\smartcs\huggingface'
$env:TORCH_HOME = 'D:\DevData\smartcs\torch'
$env:TESSERACT_CMD = 'D:\DevData\smartcs\tesseract\tesseract.exe'
$env:TESSDATA_PREFIX = 'D:\DevData\smartcs\tesseract\tessdata\'
$env:DOCLING_DEVICE = 'cpu'
$env:DOCLING_NUM_THREADS = '4'
$env:OMP_NUM_THREADS = '4'

New-Item -ItemType Directory -Force $env:PIP_CACHE_DIR, $env:DOCLING_ARTIFACTS_PATH, $env:HF_HOME, $env:TORCH_HOME, $env:TESSDATA_PREFIX | Out-Null
```

`TESSDATA_PREFIX` must end in a slash. Copy the same values into the local
`.env` only when enabling this optional parser; do not commit that file.

## Inspect and install Docling

First resolve the optional requirements without installing them. `PIP_CACHE_DIR`
must be set as above before this command so pip metadata and downloads use `D:`.

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pip install --dry-run -r requirements-docling.txt
```

After reviewing the resolver output, install the optional package:

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\python.exe' -m pip install -r requirements-docling.txt
```

Docling's base package includes its standard PDF and local-model pipeline. Do
not add OCR extras unless the parser adapter later requires a different OCR
engine.

## Prefetch local models

After Docling is installed, download the default local models directly into
the configured artifact directory:

```powershell
& 'D:\2026.07.09\conda-envs\smart-cs\Scripts\docling-tools.exe' models download --output-dir $env:DOCLING_ARTIFACTS_PATH
```

Use `--all` only when a later parser feature explicitly needs every optional
model. The future adapter must pass `DOCLING_ARTIFACTS_PATH` to Docling's PDF
pipeline options.

## Install and verify Tesseract

Install a Windows Tesseract distribution into
`D:\DevData\smartcs\tesseract` and place `chi_sim.traineddata` under
`D:\DevData\smartcs\tesseract\tessdata`. Then verify both the executable and
Simplified Chinese language data:

```powershell
& $env:TESSERACT_CMD --version
& $env:TESSERACT_CMD --list-langs
```

The second command must list `chi_sim`. Keep the executable and `tessdata`
directory together on `D:`; do not rely on a system-drive installation or a
machine-wide `PATH` entry.

## Audit cache locations before parsing

Before the first real parse, confirm that every configured location resolves
to `D:` and inspect common system-drive cache locations for unexpected new
Docling, Hugging Face, Torch, or pip data:

```powershell
@($env:PIP_CACHE_DIR, $env:DOCLING_ARTIFACTS_PATH, $env:HF_HOME, $env:TORCH_HOME, $env:TESSDATA_PREFIX) |
    ForEach-Object { Get-Item $_ | Select-Object FullName }

Get-ChildItem -Force "$env:LOCALAPPDATA\pip\Cache", "$env:USERPROFILE\.cache\huggingface", "$env:USERPROFILE\.cache\docling" -ErrorAction SilentlyContinue |
    Select-Object FullName
```

If the audit finds newly created parser data outside `D:`, stop before parsing
documents and correct the environment variables or artifact target.
