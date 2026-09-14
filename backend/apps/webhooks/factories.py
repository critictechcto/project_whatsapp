import hashlib
import json

import factory

from .models import WebhookEvent


class WebhookEventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WebhookEvent

    payload = factory.Sequence(
        lambda n: {"object": "whatsapp_business_account", "entry": [], "sequence": n}
    )
    object_type = factory.LazyAttribute(lambda o: o.payload.get("object", ""))
    body_sha256 = factory.LazyAttribute(
        lambda o: hashlib.sha256(json.dumps(o.payload, sort_keys=True).encode()).hexdigest()
    )
    status = WebhookEvent.Status.RECEIVED
