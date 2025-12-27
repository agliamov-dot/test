from __future__ import annotations

import pytest

from ded_moroz.db.models import GiftType
from ded_moroz.handlers.commands import GiftParseError, _parse_set_gift_args


def test_parse_set_gift_plain_text():
    day, gift_type, gift_text, gift_url, payload = _parse_set_gift_args("1 Привет, это тестовый подарок!")

    assert day == 1
    assert gift_type is GiftType.TEXT
    assert gift_text == "Привет, это тестовый подарок!"
    assert gift_url is None
    assert payload is None


def test_parse_set_gift_media_with_caption():
    day, gift_type, gift_text, gift_url, payload = _parse_set_gift_args(
        "2 photo https://example.com/pic.jpg Вот твой подарок!"
    )

    assert day == 2
    assert gift_type is GiftType.PHOTO
    assert gift_url == "https://example.com/pic.jpg"
    assert gift_text == "Вот твой подарок!"
    assert payload is None


def test_parse_set_gift_invalid_day():
    with pytest.raises(GiftParseError):
        _parse_set_gift_args("x текст")
