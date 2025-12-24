from ded_moroz.db.models import ErrorLog, NotificationLog, NotificationType, SeverityLevel, User, UserStatus


def test_enum_columns_use_values() -> None:
    status_enum = User.__table__.c.status.type  # type: ignore[attr-defined]
    notification_enum = NotificationLog.__table__.c.notification_type.type  # type: ignore[attr-defined]
    severity_enum = ErrorLog.__table__.c.level.type  # type: ignore[attr-defined]

    assert status_enum.enums == [item.value for item in UserStatus]
    assert notification_enum.enums == [item.value for item in NotificationType]
    assert severity_enum.enums == [item.value for item in SeverityLevel]
