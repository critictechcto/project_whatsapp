from common.apps import BaseAppConfig


class WhatsAppConfig(BaseAppConfig):
    # apps.py also exposes the imported BaseAppConfig, so Django needs an explicit default or it
    # falls back to a plain AppConfig and receivers.py is never imported.
    default = True
    name = "apps.whatsapp"
    label = "whatsapp"
    verbose_name = "WhatsApp"
