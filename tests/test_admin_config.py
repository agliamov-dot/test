from __future__ import annotations

from ded_moroz.config import AdminConfig


def test_admin_ids_accepts_tg_alias(monkeypatch):
    monkeypatch.delenv("ADMIN_IDS", raising=False)
    monkeypatch.delenv("ADMINS__IDS", raising=False)
    monkeypatch.delenv("ADMIN_ADMIN_IDS", raising=False)
    monkeypatch.setenv("ADMIN_TG_IDS", "101, 202 ,303")

    cfg = AdminConfig()

    assert cfg.admin_ids == [101, 202, 303]


def test_admin_ids_parses_csv(monkeypatch):
    monkeypatch.delenv("ADMIN_TG_IDS", raising=False)
    monkeypatch.delenv("ADMINS__IDS", raising=False)
    monkeypatch.delenv("ADMIN_ADMIN_IDS", raising=False)
    monkeypatch.setenv("ADMIN_IDS", "11,22,33")

    cfg = AdminConfig()

    assert cfg.admin_ids == [11, 22, 33]
