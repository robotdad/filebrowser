import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    home_dir: Path = field(default_factory=Path.home)
    session_timeout: int = 86400  # 24 hours in seconds
    upload_max_size: int = 1_073_741_824  # 1 GB in bytes
    secret_key: str = field(
        default_factory=lambda: os.environ.get(
            "FILEBROWSER_SECRET_KEY", secrets.token_hex(32)
        )
    )


settings = Settings()
