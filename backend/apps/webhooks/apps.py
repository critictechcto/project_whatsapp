from common.apps import BaseAppConfig


class WebhooksConfig(BaseAppConfig):
    # The module also imports BaseAppConfig; without this Django falls back to a plain AppConfig.
    default = True
    name = "apps.webhooks"
    label = "webhooks"
    verbose_name = "Webhooks"
