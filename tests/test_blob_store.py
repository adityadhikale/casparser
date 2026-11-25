"""Unit tests for the Azure Blob archive (no network: the client is faked)."""

from __future__ import annotations

import re
from concurrent.futures import Future

import pytest

import blob_store


class _SyncExecutor:
    def submit(self, fn, *args, **kwargs):
        fut: Future = Future()
        fut.set_result(fn(*args, **kwargs))
        return fut


class _FakeContainer:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls: list[dict] = []

    def upload_blob(self, **kwargs):
        if self.fail:
            raise RuntimeError("boom")
        self.calls.append(kwargs)


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "fake")
    monkeypatch.setenv("AZURE_BLOB_CONTAINER", "cas")
    monkeypatch.setattr(blob_store, "_executor", _SyncExecutor())
    fake = _FakeContainer()
    monkeypatch.setattr(blob_store, "_get_container", lambda: fake)
    return fake


def test_disabled_without_env(monkeypatch):
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("AZURE_BLOB_CONTAINER", raising=False)
    assert not blob_store.enabled()
    assert blob_store.save([("a.pdf", b"x")], "parsed", "single") == []


@pytest.mark.parametrize(
    "name, expected",
    [
        ("CAS Jan 2026.pdf", "CAS_Jan_2026.pdf"),
        ("..\\..\\evil/../x.PDF", "x.PDF"),
        ("statement", "statement.pdf"),
        ("राम.pdf", "pdf.pdf"),
        (None, "statement.pdf"),
        ("", "statement.pdf"),
    ],
)
def test_safe_filename(name, expected):
    assert blob_store.safe_filename(name) == expected


def test_safe_filename_caps_length():
    out = blob_store.safe_filename("a" * 300 + ".pdf")
    assert len(out) == 100 and out.endswith(".pdf")


def test_single_upload(configured):
    paths = blob_store.save([("My CAS.pdf", b"%PDF")], "parsed", "single")
    assert len(paths) == 1
    assert re.fullmatch(r"parsed/\d{4}/\d{2}/\d{2}/\d{6}_[0-9a-f]{8}/My_CAS\.pdf", paths[0])
    call = configured.calls[0]
    assert call["name"] == paths[0]
    assert call["data"] == b"%PDF"
    assert call["overwrite"] is False
    assert call["content_settings"].content_type == "application/pdf"
    assert call["metadata"] == {"kind": "single", "original_name": "My CAS.pdf"}


def test_family_shares_folder_and_dedupes(configured):
    paths = blob_store.save([("a.pdf", b"1"), ("a.pdf", b"2"), ("b.pdf", b"3")], "failed", "family")
    folders = {p.rsplit("/", 1)[0] for p in paths}
    assert len(folders) == 1 and paths[0].startswith("failed/")
    assert [p.rsplit("/", 1)[1] for p in paths] == ["a.pdf", "2_a.pdf", "b.pdf"]
    assert len(configured.calls) == 3


def test_upload_error_is_swallowed(monkeypatch, configured, caplog):
    monkeypatch.setattr(blob_store, "_get_container", lambda: _FakeContainer(fail=True))
    with caplog.at_level("ERROR", logger="blob_store"):
        paths = blob_store.save([("a.pdf", b"1")], "parsed", "single")
    assert paths and "Azure Blob upload failed" in caplog.text
