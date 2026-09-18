"""Public registration cannot grant a requested administrator role."""

from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.user import UserCreate
from app.services.user import UserService


@pytest.mark.anyio
@pytest.mark.parametrize("first_user,expected_role", [(True, "admin"), (False, "user")])
async def test_registration_controls_role(first_user, expected_role):
    service = UserService(AsyncMock())
    payload = UserCreate(email="role-check@example.com", password="test-password-123", role="admin")
    with (
        patch.object(service, "_is_first_user", AsyncMock(return_value=first_user)),
        patch("app.services.user.user_repo.get_by_email", AsyncMock(return_value=None)),
        patch("app.services.user.user_repo.create", AsyncMock()) as create,
        patch("app.services.user.get_password_hash", return_value="hashed"),
    ):
        await service.register(payload)
    assert create.call_args.kwargs["role"] == expected_role
