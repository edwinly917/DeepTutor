from __future__ import annotations

import pytest

from src.services.export.source_report import SourceReportGenerator


def test_ssrf_guard_rejects_private_ip_targets(monkeypatch):
    generator = SourceReportGenerator()

    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, port, type=0: [
            (2, 1, 6, "", ("127.0.0.1", port)),
            (2, 1, 6, "", ("10.0.0.7", port)),
        ],
    )

    with pytest.raises(ValueError, match="non-public network"):
        generator._validate_safe_fetch_url("https://example.com/path")


def test_ssrf_guard_rejects_non_http_schemes():
    generator = SourceReportGenerator()

    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        generator._validate_safe_fetch_url("file:///etc/passwd")
