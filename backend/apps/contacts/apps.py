from common.apps import BaseAppConfig


class ContactsConfig(BaseAppConfig):
    # apps.py also exposes the imported BaseAppConfig; without `default` Django falls back to a
    # plain AppConfig and receivers.py is never imported.
    default = True
    name = "apps.contacts"
    label = "contacts"
    verbose_name = "Contacts"
