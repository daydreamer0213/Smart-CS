# Docling and Tesseract Setup

Docling and Tesseract are optional local dependencies. The supported local
Windows profile keeps package caches, model artifacts, and OCR language data
under `D:\DevData\smartcs`. Do not add this optional dependency to
`requirements.txt`.

SmartCS uses the configured Tesseract CLI only for OCR. Do not enable an
automatic or alternate OCR backend.

## Set the local paths

Run these commands in PowerShell from the repository root. They only set
environment variables for the current shell.

```powershell
$env:PIP_CACHE_DIR = 'D:\DevData\smartcs\pip'
$env:PARSER_DATA_ROOT = 'D:\DevData\smartcs'
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

`TESSDATA_PREFIX` is normalized to end in a slash. All parser paths must be
children of `PARSER_DATA_ROOT`; the default therefore confines them to
`D:\DevData\smartcs`. A non-Windows deployment may set an explicit absolute
root and matching child paths. Copy the same values into the local `.env` only
when enabling this optional parser; do not commit that file.

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

The optional requirement is deliberately limited to Docling PDF support and
local models. It does not select an OCR backend; OCR remains the configured
Tesseract CLI only.

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
`D:\DevData\smartcs\tesseract` and place both `eng.traineddata` and
`chi_sim.traineddata` under `D:\DevData\smartcs\tesseract\tessdata`. Then
verify the executable and require both languages:

```powershell
& $env:TESSERACT_CMD --version
$languages = & $env:TESSERACT_CMD --tessdata-dir $env:TESSDATA_PREFIX --list-langs
$missing = @('eng', 'chi_sim') | Where-Object { $_ -notin $languages }
if ($missing) { throw "Missing Tesseract languages: $($missing -join ', ')" }
```

The language check must succeed for both `eng` and `chi_sim`. Keep the
executable and `tessdata` directory together under `PARSER_DATA_ROOT`; do not
rely on a system-drive installation or a machine-wide `PATH` entry.

## Audit cache locations before parsing

Before the first real parse, confirm that every configured location resolves
to `D:` and inspect common system-drive cache locations for unexpected new
Docling, Hugging Face, Torch, or pip data:

```powershell
@($env:PIP_CACHE_DIR, $env:PARSER_DATA_ROOT, $env:DOCLING_ARTIFACTS_PATH, $env:HF_HOME, $env:TORCH_HOME, $env:TESSDATA_PREFIX) |
    ForEach-Object { Get-Item $_ | Select-Object FullName }

Get-ChildItem -Force "$env:LOCALAPPDATA\pip\Cache", "$env:USERPROFILE\.cache\huggingface", "$env:USERPROFILE\.cache\docling" -ErrorAction SilentlyContinue |
    Select-Object FullName
```

For the supported Windows profile, if the audit finds newly created parser
data outside `D:\DevData\smartcs`, stop before parsing documents and correct
the environment variables or artifact target.
