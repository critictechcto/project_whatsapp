from django.core.signals import setting_changed
from django.dispatch import receiver

from common.crypto import get_fernet


@receiver(setting_changed)
def reset_fernet_cache(sender, setting, **kwargs):
    if setting == "TOKEN_ENCRYPTION_KEYS":
        get_fernet.cache_clear()
