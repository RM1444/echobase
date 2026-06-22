"""No-network / air-gapped verification (thesis section 3.2, reframed).

EchoBase is fully local, so the source plan's cloud->edge failover is replaced by
a privacy verification: with outbound networking blocked, command handling still
works and nothing attempts an outbound connection. We also audit the source to
confirm the single documented network seam -- the Piper voice download in
``config.py`` -- is the ONLY outbound-network code path.

This is the in-process guard form; the README documents running the whole app
under a real network namespace (``unshare -n``) for the end-to-end air-gapped run.
"""

from __future__ import annotations

import contextlib
import io
import re
import socket
import urllib.request
from pathlib import Path

import pytest

from EchoBase.core import main as ebmain
from validation.harness.echobase_factory import build_core, neutralized_subprocess

SRC_DIR = Path(__file__).resolve().parents[3] / "src"

# Outbound-network APIs. Local IPC (subprocess, AF_UNIX D-Bus) is NOT network.
NET_PATTERN = re.compile(
    r"\b(urlopen|urlretrieve|requests\.(get|post|put)|httpx\.|aiohttp|"
    r"create_connection|http\.client|ftplib|smtplib)\b"
)
# Files allowed to contain the documented outbound seam (Piper voice download).
ALLOWED_NETWORK_FILES = {"config.py"}


@pytest.fixture
def block_outbound(monkeypatch):
    """Raise on any outbound INET connection or urlopen; allow AF_UNIX (D-Bus)."""
    tripped = {"hit": None}
    orig_connect = socket.socket.connect

    def guarded_connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            tripped["hit"] = address
            raise AssertionError(f"outbound network attempt to {address}")
        return orig_connect(self, address)

    def guarded_urlopen(*_a, **_k):
        tripped["hit"] = "urlopen"
        raise AssertionError("outbound urlopen attempt")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(urllib.request, "urlopen", guarded_urlopen)
    return tripped


class TestRuntimeOffline:
    def test_build_and_route_make_no_network(self, block_outbound):
        commands = [
            "open firefox", "play", "volume up", "scroll down", "minimize",
            "copy", "what day is it", "opn firefox", "xqzptv",
        ]
        with neutralized_subprocess(), contextlib.redirect_stdout(io.StringIO()):
            core = build_core()
            for cmd in commands:
                ebmain.EchoBase._dispatch(core, cmd, skip_blocking=True)
        assert block_outbound["hit"] is None, (
            f"command handling attempted an outbound connection: {block_outbound['hit']}"
        )


class TestSourceAudit:
    def test_single_network_seam(self):
        offenders: dict[str, list[str]] = {}
        for path in SRC_DIR.rglob("*.py"):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if NET_PATTERN.search(stripped):
                    offenders.setdefault(path.name, []).append(f"{lineno}: {stripped}")
        unexpected = {f: v for f, v in offenders.items() if f not in ALLOWED_NETWORK_FILES}
        assert not unexpected, (
            "outbound-network code outside the documented seam "
            f"({ALLOWED_NETWORK_FILES}): {unexpected}"
        )

    def test_documented_seam_exists(self):
        from EchoBase.core import config as ebconfig

        # The single seam: a private downloader used only by the voice-ensure path.
        assert hasattr(ebconfig, "_download"), "expected config._download voice seam"

    def test_init_path_does_not_download(self, block_outbound):
        """Constructing the core (ensure=False) must not fetch anything."""
        with contextlib.redirect_stdout(io.StringIO()):
            build_core()
        assert block_outbound["hit"] is None
