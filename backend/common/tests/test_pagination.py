import pytest
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.tenants.factories import MembershipFactory
from apps.tenants.models import Membership
from common.pagination import DefaultCursorPagination

factory = APIRequestFactory()


def test_configuration(settings):
    assert DefaultCursorPagination.page_size == 50
    assert DefaultCursorPagination.max_page_size == 200
    assert DefaultCursorPagination.page_size_query_param == "page_size"
    assert DefaultCursorPagination.ordering == "-created_at"
    assert (
        settings.REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]
        == "common.pagination.DefaultCursorPagination"
    )


@pytest.mark.parametrize(("requested", "expected"), [(None, 50), ("10", 10), ("1000", 200)])
def test_page_size(requested, expected):
    params = {"page_size": requested} if requested else {}
    request = Request(factory.get("/", params))

    assert DefaultCursorPagination().get_page_size(request) == expected


@pytest.mark.django_db
def test_paginates_newest_first(workspace):
    MembershipFactory.create_batch(3, workspace=workspace)
    paginator = DefaultCursorPagination()
    request = Request(factory.get("/", {"page_size": 2}))

    page = paginator.paginate_queryset(Membership.objects.filter(workspace=workspace), request)

    assert len(page) == 2
    created = [membership.created_at for membership in page]
    assert created == sorted(created, reverse=True)
    assert paginator.get_next_link() is not None
    assert paginator.get_previous_link() is None
