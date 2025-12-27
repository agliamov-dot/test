from __future__ import annotations

from types import SimpleNamespace

from ded_moroz.db.models import GiftType
from ded_moroz.handlers.commands import _format_gift_line, _gift_caption


def test_format_gift_text_and_photo():
    gift = SimpleNamespace(
        gift_type=GiftType.PHOTO,
        gift_text="Текст подарка",
        gift_url="https://example.com/pic.jpg",
        payload=None,
    )

    assert _format_gift_line(gift) == "Текст подарка\nhttps://example.com/pic.jpg"


def test_format_gift_payload():
    gift = SimpleNamespace(
        gift_type=GiftType.PAYLOAD,
        payload={"key": "value"},
        gift_text=None,
        gift_url=None,
    )

    assert _format_gift_line(gift) == '{"key": "value"}'


def test_gift_caption_media_does_not_leak_file_id():
    gift = SimpleNamespace(
        gift_type=GiftType.PHOTO,
        gift_text="Подпись",
        gift_url="AgACAgIA...",
        payload=None,
    )

    caption = _gift_caption(gift, llm_reply=None)

    assert "AgACAgIA" not in caption
    assert "Подпись" in caption
