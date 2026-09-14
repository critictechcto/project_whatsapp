import django_filters

from .models import Contact


class ContactFilter(django_filters.FilterSet):
    tag = django_filters.UUIDFilter(field_name="tags__id", label="Tag id")

    class Meta:
        model = Contact
        fields = ("tag", "marketing_opt_in_status")
