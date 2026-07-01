from pathlib import Path


def test_settings_has_correct_defaults():
    from filebrowser.config import Settings

    s = Settings()
    assert s.home_dir == Path.home()
    assert s.session_timeout == 2592000
    assert s.upload_max_size == 1_073_741_824
    assert isinstance(s.secret_key, str)
    assert len(s.secret_key) >= 32
    assert s.secure_cookies is False


def test_settings_accepts_custom_values(tmp_path):
    from filebrowser.config import Settings

    s = Settings(
        home_dir=tmp_path,
        session_timeout=3600,
        upload_max_size=500,
        secret_key="my-test-secret",
    )
    assert s.home_dir == tmp_path
    assert s.session_timeout == 3600
    assert s.upload_max_size == 500
    assert s.secret_key == "my-test-secret"


def test_settings_reads_secret_from_env(monkeypatch):
    from filebrowser.config import Settings

    monkeypatch.setenv("FILEBROWSER_SECRET_KEY", "env-secret-value")
    s = Settings()
    assert s.secret_key == "env-secret-value"


def test_settings_reads_secret_from_file(tmp_path, monkeypatch):
    """Test that secret key is read from file."""
    from filebrowser.config import Settings
    
    # Create secret key file
    config_dir = tmp_path / ".config" / "filebrowser"
    config_dir.mkdir(parents=True)
    secret_file = config_dir / "secret_key"
    secret_file.write_text("file-secret-value")
    
    monkeypatch.setenv("FILEBROWSER_DATA_DIR", str(config_dir))
    monkeypatch.delenv("FILEBROWSER_SECRET_KEY", raising=False)
    
    s = Settings()
    assert s.secret_key == "file-secret-value"


def test_settings_reads_secret_from_env_file_path(tmp_path, monkeypatch):
    """Test that secret key is read from custom file path in env."""
    from filebrowser.config import Settings
    
    # Create secret key file in custom location
    custom_file = tmp_path / "custom_secret"
    custom_file.write_text("custom-secret-value")
    
    monkeypatch.setenv("FILEBROWSER_SECRET_KEY_FILE", str(custom_file))
    monkeypatch.delenv("FILEBROWSER_SECRET_KEY", raising=False)
    
    s = Settings()
    assert s.secret_key == "custom-secret-value"


def test_settings_env_var_takes_precedence(tmp_path, monkeypatch):
    """Test that FILEBROWSER_SECRET_KEY env var takes precedence over file."""
    from filebrowser.config import Settings
    
    # Create secret key file
    config_dir = tmp_path / ".config" / "filebrowser"
    config_dir.mkdir(parents=True)
    secret_file = config_dir / "secret_key"
    secret_file.write_text("file-secret-value")
    
    monkeypatch.setenv("FILEBROWSER_DATA_DIR", str(config_dir))
    monkeypatch.setenv("FILEBROWSER_SECRET_KEY", "env-secret-value")
    
    s = Settings()
    assert s.secret_key == "env-secret-value"


def test_settings_generates_secret_if_no_file(tmp_path, monkeypatch):
    """Test that secret key is generated if no file exists."""
    from filebrowser.config import Settings
    
    config_dir = tmp_path / ".config" / "filebrowser"
    config_dir.mkdir(parents=True)
    
    monkeypatch.setenv("FILEBROWSER_DATA_DIR", str(config_dir))
    monkeypatch.delenv("FILEBROWSER_SECRET_KEY", raising=False)
    monkeypatch.delenv("FILEBROWSER_SECRET_KEY_FILE", raising=False)
    
    s = Settings()
    assert isinstance(s.secret_key, str)
    assert len(s.secret_key) == 64  # 32 bytes hex = 64 chars
