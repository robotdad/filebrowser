import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


def _load_secret_key() -> str:
    """Load secret key from environment, file, or generate a new one."""
    # First check environment variable
    env_key = os.environ.get("FILEBROWSER_SECRET_KEY")
    if env_key:
        return env_key
    
    # Check for secret key file path in environment
    secret_key_file_env = os.environ.get("FILEBROWSER_SECRET_KEY_FILE")
    if secret_key_file_env:
        secret_key_file = Path(secret_key_file_env)
        if secret_key_file.exists():
            return secret_key_file.read_text().strip()
    
    # Check default location
    data_dir = Path(
        os.environ.get(
            "FILEBROWSER_DATA_DIR", str(Path.home() / ".config" / "filebrowser")
        )
    )
    secret_key_file = data_dir / "secret_key"
    
    if secret_key_file.exists():
        return secret_key_file.read_text().strip()
    
    # Generate a new secret key (ephemeral, for development)
    # In production, the service installer should create this file
    return secrets.token_hex(32)


@dataclass
class Settings:
    home_dir: Path = field(default_factory=Path.home)
    data_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get(
                "FILEBROWSER_DATA_DIR", str(Path.home() / ".config" / "filebrowser")
            )
        )
    )
    session_timeout: int = 2592000  # 30 days in seconds
    upload_max_size: int = 1_073_741_824  # 1 GB in bytes
    secret_key: str = field(default_factory=_load_secret_key)
    secure_cookies: bool = field(
        default_factory=lambda: (
            os.environ.get("FILEBROWSER_SECURE_COOKIES", "false").lower() == "true"
        )
    )
    terminal_enabled: bool = field(
        default_factory=lambda: (
            os.environ.get("FILEBROWSER_TERMINAL_ENABLED", "true").lower() == "true"
        )
    )
    log_level: str = field(
        default_factory=lambda: os.environ.get("FILEBROWSER_LOG_LEVEL", "info")
    )


settings = Settings()
