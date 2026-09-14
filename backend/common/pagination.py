from rest_framework.pagination import CursorPagination


class DefaultCursorPagination(CursorPagination):
    """Stable pagination for large, frequently-written tables. Requires a ``created_at`` field
    (or override ``ordering`` on the view)."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
    ordering = "-created_at"
