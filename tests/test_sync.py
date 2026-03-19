"""Tests unitaires pour les fonctions utilitaires de check_repos."""

from __future__ import annotations

import pytest
from check_repos.sync import (
    best_version,
    normalize_tag,
    parse_version_from_pyproject,
    parse_name_from_pyproject,
    source_status,
    version_key,
)


class TestParseVersionFromPyproject:
    def test_simple(self):
        text = '[project]\nname = "mypkg"\nversion = "1.2.3"\n'
        assert parse_version_from_pyproject(text) == "1.2.3"

    def test_single_quotes(self):
        text = "[project]\nversion = '0.1.0'\n"
        assert parse_version_from_pyproject(text) == "0.1.0"

    def test_missing_raises(self):
        with pytest.raises(ValueError):
            parse_version_from_pyproject("[project]\nname = 'foo'\n")

    def test_stops_at_next_section(self):
        text = "[project]\nversion = '1.0.0'\n\n[tool.something]\nversion = '9.9.9'\n"
        assert parse_version_from_pyproject(text) == "1.0.0"


class TestParseNameFromPyproject:
    def test_simple(self):
        text = '[project]\nname = "my-package"\nversion = "1.0.0"\n'
        assert parse_name_from_pyproject(text) == "my-package"


class TestNormalizeTag:
    def test_none_returns_none(self):
        assert normalize_tag(None) is None

    def test_strips_v_prefix(self):
        assert normalize_tag("v1.2.3") == "1.2.3"

    def test_uppercase_v(self):
        assert normalize_tag("V2.0.0") == "2.0.0"

    def test_no_prefix(self):
        assert normalize_tag("1.2.3") == "1.2.3"

    def test_bare_v_returns_none(self):
        assert normalize_tag("v") is None


class TestBestVersion:
    def test_picks_highest(self):
        assert best_version(["1.0.0", "2.0.0", "1.5.0"]) == "2.0.0"

    def test_filters_empty(self):
        assert best_version(["", "1.0.0", None]) == "1.0.0"

    def test_empty_returns_none(self):
        assert best_version([]) is None

    def test_single(self):
        assert best_version(["0.3.1"]) == "0.3.1"


class TestSourceStatus:
    def test_ok(self):
        assert source_status("1.0.0", "1.0.0") == "OK"

    def test_outdated(self):
        assert source_status("0.9.0", "1.0.0") == "OUTDATED"

    def test_missing(self):
        assert source_status(None, "1.0.0") == "MISSING"

    def test_unknown_when_expected_none(self):
        assert source_status(None, None) == "UNKNOWN"
