from pathlib import Path


def test_settings_has_correct_defaults():
    from filebrowser.config import Settings

    s = Settings()
    assert s.home_dir == Path.home()
    assert s.session_timeout == 86400
    assert s.upload_max_size == 1_073_741_824
    assert isinstance(s.secret_key, str)
    assert len(s.secret_key) >= 32


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
