"""Tests for the XDG autostart helpers in ``config`` (start on login).

``set_autostart`` is pointed at a temp directory via ``monkeypatch`` so no real
``~/.config/autostart`` entry is touched."""

import pytest
from EchoBase.core import config


@pytest.fixture
def autostart_paths(tmp_path, monkeypatch):
    """Redirect the autostart dir/file at module level to a temp location."""
    autostart_dir = tmp_path / "autostart"
    autostart_file = autostart_dir / "echobase.desktop"
    monkeypatch.setattr(config, "AUTOSTART_DIR", autostart_dir)
    monkeypatch.setattr(config, "AUTOSTART_FILE", autostart_file)
    return autostart_file


def test_set_autostart_enable_creates_valid_desktop_entry(autostart_paths):
    assert config.set_autostart(True) is True
    assert config.autostart_enabled() is True
    text = autostart_paths.read_text()
    assert text.startswith("[Desktop Entry]")
    assert "Type=Application" in text
    assert "Exec=" in text
    assert "X-GNOME-Autostart-enabled=true" in text


def test_set_autostart_disable_removes_entry(autostart_paths):
    config.set_autostart(True)
    assert config.autostart_enabled() is True
    assert config.set_autostart(False) is True
    assert config.autostart_enabled() is False


def test_set_autostart_disable_is_idempotent(autostart_paths):
    # Removing when nothing is there must not raise and reports success.
    assert config.autostart_enabled() is False
    assert config.set_autostart(False) is True


def test_set_autostart_returns_false_on_oserror(autostart_paths, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("read-only filesystem")

    monkeypatch.setattr(config.Path, "mkdir", boom)
    assert config.set_autostart(True) is False


def test_autostart_command_prefers_installed_script(monkeypatch):
    monkeypatch.setattr(config.shutil, "which", lambda name: "/usr/bin/EchoBase")
    assert config.autostart_command() == "/usr/bin/EchoBase"


def test_autostart_command_falls_back_when_not_on_path(monkeypatch):
    monkeypatch.setattr(config.shutil, "which", lambda name: None)
    cmd = config.autostart_command()
    # Either the dev launcher script or a module re-run, but always something.
    assert cmd
    assert "echobase.sh" in cmd or "EchoBase.core.main" in cmd
