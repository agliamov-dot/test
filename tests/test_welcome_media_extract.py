from __future__ import annotations

from types import SimpleNamespace

from ded_moroz.db.models import GiftType
from ded_moroz.handlers.commands import _extract_media_from_message


def test_extracts_image_document():
    message = SimpleNamespace(
        photo=None,
        video=None,
        audio=None,
        document=SimpleNamespace(mime_type="image/png", file_id="doc-image-id"),
    )

    media_type, media_id = _extract_media_from_message(message)

    assert media_type is GiftType.PHOTO
    assert media_id == "doc-image-id"


def test_extracts_audio():
    message = SimpleNamespace(
        photo=None,
        video=None,
        audio=SimpleNamespace(file_id="audio-id"),
        document=None,
    )

    media_type, media_id = _extract_media_from_message(message)

    assert media_type is GiftType.AUDIO
    assert media_id == "audio-id"
