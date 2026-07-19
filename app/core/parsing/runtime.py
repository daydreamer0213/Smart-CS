"""Process runtime configuration for optional document parsers."""

import os
import tempfile
from pathlib import Path

from app.config import Settings, settings


def configure_parser_runtime(config: Settings | None = None) -> None:
    """Apply configured parser cache and temporary paths to this process."""
    config = config or settings
    Path(config.parser_temp_dir).mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = config.parser_temp_dir
    os.environ.update(
        {
            "TEMP": config.parser_temp_dir,
            "TMP": config.parser_temp_dir,
            "HF_HOME": config.hf_home,
            "TORCH_HOME": config.torch_home,
            "TESSDATA_PREFIX": config.tessdata_prefix,
        }
    )
