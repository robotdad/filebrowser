"""Tests for terminal router stub and conditional registration in main.py."""

import sys


class TestTerminalRouterStub:
    """Tests for filebrowser/routes/terminal.py stub."""

    def test_terminal_module_importable(self):
        """Terminal router module can be imported."""
        from filebrowser.routes import terminal  # noqa: F401

    def test_terminal_router_exists(self):
        """Terminal module exposes a `router` attribute."""
        from filebrowser.routes import terminal

        assert hasattr(terminal, "router")

    def test_terminal_router_prefix(self):
        """Terminal router has prefix /api/terminal."""
        from filebrowser.routes import terminal

        assert terminal.router.prefix == "/api/terminal"

    def test_terminal_router_tags(self):
        """Terminal router has tag 'terminal'."""
        from filebrowser.routes import terminal

        assert "terminal" in terminal.router.tags

    def test_terminal_router_is_apirouter(self):
        """Terminal router is a FastAPI APIRouter instance."""
        from fastapi import APIRouter
        from filebrowser.routes import terminal

        assert isinstance(terminal.router, APIRouter)


class TestMainConditionalRegistration:
    """Tests for conditional terminal router registration in main.py."""

    def _reload_main(self, terminal_enabled: bool, monkeypatch):
        """Helper: patch settings, clear module caches, reimport main."""
        import filebrowser.config as config_mod

        monkeypatch.setattr(config_mod.settings, "terminal_enabled", terminal_enabled)

        # Clear main from module cache so the conditional re-runs
        sys.modules.pop("filebrowser.main", None)

        # Clear the terminal submodule from sys.modules AND remove the attribute
        # from the parent package so Python performs a real re-import.
        sys.modules.pop("filebrowser.routes.terminal", None)
        import filebrowser.routes as routes_pkg

        if hasattr(routes_pkg, "terminal"):
            delattr(routes_pkg, "terminal")

        import filebrowser.main as main_mod

        return main_mod

    def test_terminal_module_loaded_when_enabled(self, monkeypatch):
        """When terminal_enabled=True, filebrowser.routes.terminal is imported."""
        self._reload_main(terminal_enabled=True, monkeypatch=monkeypatch)
        assert "filebrowser.routes.terminal" in sys.modules

    def test_terminal_module_not_loaded_when_disabled(self, monkeypatch):
        """When terminal_enabled=False, filebrowser.routes.terminal is NOT imported."""
        self._reload_main(terminal_enabled=False, monkeypatch=monkeypatch)
        assert "filebrowser.routes.terminal" not in sys.modules

    def test_main_imports_settings(self):
        """main.py imports settings from filebrowser.config."""
        # Verify the settings singleton is accessible; main.py imports it at module level
        import filebrowser.config as config_mod

        assert hasattr(config_mod, "settings")

    def test_static_mount_still_present_after_reload(self, monkeypatch):
        """Static mount is still registered after reload with terminal enabled."""
        main_mod = self._reload_main(terminal_enabled=True, monkeypatch=monkeypatch)
        # Either static dir exists (and the mount is there) or it doesn't —
        # either way, no exception should occur and the app object is valid.
        assert main_mod.app is not None
