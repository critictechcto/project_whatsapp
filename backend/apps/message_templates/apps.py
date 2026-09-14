from common.apps import BaseAppConfig


class MessageTemplatesConfig(BaseAppConfig):
    # BaseAppConfig is also importable from this module; without ``default`` Django can't pick
    # between the two, falls back to a plain AppConfig and receivers.py is never imported.
    default = True
    name = "apps.message_templates"
    label = "message_templates"
    verbose_name = "Message templates"
