"""Tests for the security guardrails in guaraci.core.security."""

from pathlib import Path

import pytest

from guaraci.core.security import (
    CRAWL_ALLOWLIST_ENV,
    OUTPUT_ROOT_ENV,
    ensure_allowed_crawl_url,
    ensure_allowed_output_dir,
)


class TestEnsureAllowedCrawlUrl:
    def test_none_and_empty_are_accepted(self):
        ensure_allowed_crawl_url(None)
        ensure_allowed_crawl_url("")
        ensure_allowed_crawl_url("   ")

    def test_gov_br_default_domain_accepted(self):
        ensure_allowed_crawl_url("https://www.gov.br/mdr/pt-br/assuntos/sinisa")
        ensure_allowed_crawl_url("http://gov.br/algo")

    def test_non_gov_br_rejected(self):
        with pytest.raises(ValueError, match="not in the allowed domains"):
            ensure_allowed_crawl_url("https://evil.example.com/steal")

    def test_lookalike_suffix_rejected(self):
        with pytest.raises(ValueError, match="not in the allowed domains"):
            ensure_allowed_crawl_url("https://notgov.br.example.com/")
        with pytest.raises(ValueError, match="not in the allowed domains"):
            ensure_allowed_crawl_url("https://fakegov.br/")

    def test_internal_address_rejected(self):
        with pytest.raises(ValueError):
            ensure_allowed_crawl_url("http://169.254.169.254/latest/meta-data")
        with pytest.raises(ValueError):
            ensure_allowed_crawl_url("http://localhost:8002/jobs")

    def test_non_http_scheme_rejected(self):
        with pytest.raises(ValueError, match="scheme"):
            ensure_allowed_crawl_url("file:///etc/passwd")
        with pytest.raises(ValueError, match="scheme"):
            ensure_allowed_crawl_url("ftp://ftp.datasus.gov.br/x")

    def test_allowlist_env_extends_domains(self, monkeypatch):
        monkeypatch.setenv(CRAWL_ALLOWLIST_ENV, "example.org, .other.net")
        ensure_allowed_crawl_url("https://data.example.org/page")
        ensure_allowed_crawl_url("https://sub.other.net/page")
        with pytest.raises(ValueError):
            ensure_allowed_crawl_url("https://example.net/page")


class TestEnsureAllowedOutputDir:
    def test_unrestricted_when_env_unset(self, monkeypatch, tmp_path):
        monkeypatch.delenv(OUTPUT_ROOT_ENV, raising=False)
        ensure_allowed_output_dir(tmp_path / "anywhere")
        ensure_allowed_output_dir("/qualquer/lugar")

    def test_none_and_empty_accepted(self, monkeypatch, tmp_path):
        monkeypatch.setenv(OUTPUT_ROOT_ENV, str(tmp_path))
        ensure_allowed_output_dir(None)
        ensure_allowed_output_dir("")

    def test_inside_root_accepted(self, monkeypatch, tmp_path):
        monkeypatch.setenv(OUTPUT_ROOT_ENV, str(tmp_path))
        ensure_allowed_output_dir(tmp_path)
        ensure_allowed_output_dir(tmp_path / "sub" / "dir")

    def test_outside_root_rejected(self, monkeypatch, tmp_path):
        root = tmp_path / "allowed"
        root.mkdir()
        monkeypatch.setenv(OUTPUT_ROOT_ENV, str(root))
        with pytest.raises(ValueError, match="outside the allowed output root"):
            ensure_allowed_output_dir(tmp_path / "forbidden")

    def test_traversal_rejected(self, monkeypatch, tmp_path):
        root = tmp_path / "allowed"
        root.mkdir()
        monkeypatch.setenv(OUTPUT_ROOT_ENV, str(root))
        with pytest.raises(ValueError, match="outside the allowed output root"):
            ensure_allowed_output_dir(str(root / ".." / "forbidden"))

    def test_prefix_sibling_rejected(self, monkeypatch, tmp_path):
        root = tmp_path / "allowed"
        root.mkdir()
        monkeypatch.setenv(OUTPUT_ROOT_ENV, str(root))
        # "allowed-evil" compartilha prefixo textual mas não é subdiretório.
        with pytest.raises(ValueError, match="outside the allowed output root"):
            ensure_allowed_output_dir(str(tmp_path / "allowed-evil"))


class TestDownloadServiceIntegration:
    def test_validate_rejects_bad_results_url(self):
        from guaraci.services.downloads import DownloadService

        service = DownloadService()
        with pytest.raises(ValueError, match="not in the allowed domains"):
            service.validate_source_params(
                "snis", {"results_url": "https://evil.example.com/"}
            )

    def test_validate_rejects_output_dir_outside_root(self, monkeypatch, tmp_path):
        from guaraci.services.downloads import DownloadService

        root = tmp_path / "allowed"
        root.mkdir()
        monkeypatch.setenv(OUTPUT_ROOT_ENV, str(root))
        service = DownloadService()
        with pytest.raises(ValueError, match="outside the allowed output root"):
            service.validate_source_params(
                "snis", {"output_dir": str(tmp_path / "forbidden")}
            )
