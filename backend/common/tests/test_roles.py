import pytest

from common.roles import ROLE_RANK, Role, role_at_least


@pytest.mark.parametrize(
    ("role", "minimum", "expected"),
    [
        (Role.OWNER, Role.OWNER, True),
        (Role.OWNER, Role.ADMIN, True),
        (Role.OWNER, Role.AGENT, True),
        (Role.OWNER, Role.VIEWER, True),
        (Role.ADMIN, Role.OWNER, False),
        (Role.ADMIN, Role.ADMIN, True),
        (Role.ADMIN, Role.AGENT, True),
        (Role.ADMIN, Role.VIEWER, True),
        (Role.AGENT, Role.OWNER, False),
        (Role.AGENT, Role.ADMIN, False),
        (Role.AGENT, Role.AGENT, True),
        (Role.AGENT, Role.VIEWER, True),
        (Role.VIEWER, Role.OWNER, False),
        (Role.VIEWER, Role.ADMIN, False),
        (Role.VIEWER, Role.AGENT, False),
        (Role.VIEWER, Role.VIEWER, True),
    ],
)
def test_role_at_least_matrix(role, minimum, expected):
    assert role_at_least(role, minimum) is expected


def test_plain_strings_work():
    assert role_at_least("admin", "agent") is True
    assert role_at_least("viewer", "agent") is False


@pytest.mark.parametrize("role", ["", "superuser", None])
@pytest.mark.parametrize("minimum", list(Role))
def test_unknown_role_never_qualifies(role, minimum):
    assert role_at_least(role, minimum) is False


def test_every_role_has_a_rank():
    assert set(ROLE_RANK) == set(Role)
    assert [Role(value) for value in ("owner", "admin", "agent", "viewer")] == sorted(
        Role, key=ROLE_RANK.__getitem__, reverse=True
    )
