from apps.campaigns import variables
from apps.contacts.models import Contact
from apps.message_templates.models import MessageTemplate

BUTTON_TEMPLATE = [
    {"type": "HEADER", "format": "TEXT", "text": "Hello {{1}}"},
    {"type": "BODY", "text": "Hi {{1}}, the sale ends {{2}}."},
    {
        "type": "BUTTONS",
        "buttons": [
            {"type": "URL", "text": "Shop", "url": "https://shop.example.in/{{1}}"},
            {"type": "QUICK_REPLY", "text": "Stop promotions"},
            {"type": "PHONE_NUMBER", "text": "Call us", "phone_number": "+919800000000"},
            {"type": "COPY_CODE", "example": "SAVE10"},
        ],
    },
]


def source(value="x", kind="static", fallback=""):
    return {"source": kind, "value": value, "fallback": fallback}


def template(components, category=MessageTemplate.Category.MARKETING):
    return MessageTemplate(name="t", language="en", category=category, components=components)


def test_template_slots():
    slots = variables.template_slots(template(BUTTON_TEMPLATE))

    assert slots.body == 2
    assert slots.header == variables.HEADER_TEXT
    assert slots.buttons == {0: True, 1: False, 3: True}


def test_mapping_errors_report_missing_and_extra_values():
    mapping = {"body": [source()], "header": None, "buttons": {"2": source(), "1": source()}}

    errors = variables.mapping_errors(template(BUTTON_TEMPLATE), mapping)

    assert set(errors) == {"body", "header", "buttons"}
    assert "Button 2 takes no variable." in errors["buttons"]
    assert "Map a value for button 0." in errors["buttons"]
    assert "Map a value for button 3." in errors["buttons"]


def test_complete_mapping_has_no_errors():
    mapping = {
        "body": [source(), source()],
        "header": source(),
        "buttons": {"0": source(), "3": source()},
    }

    assert variables.mapping_errors(template(BUTTON_TEMPLATE), mapping) == {}


def test_header_rules():
    no_variable = template([{"type": "BODY", "text": "Sale is live."}])
    location = template(
        [{"type": "HEADER", "format": "LOCATION"}, {"type": "BODY", "text": "Visit us."}]
    )
    mapping = {"body": [], "header": source(), "buttons": {}}

    assert "header" in variables.mapping_errors(no_variable, mapping)
    assert "location" in variables.mapping_errors(location, mapping)["header"][0]


def test_media_header_value_is_sent_as_a_link():
    image = template(
        [{"type": "HEADER", "format": "IMAGE"}, {"type": "BODY", "text": "Hi {{1}}, new arrivals."}]
    )
    params = {"body": ["Asha"], "header": "https://cdn.example.in/p.jpg", "buttons": {"0": "X"}}

    content = variables.template_content(image, params)

    assert content.header_param == {"link": "https://cdn.example.in/p.jpg"}
    assert content.body_params == ("Asha",)
    assert content.button_params == {0: "X"}


def test_authentication_templates_take_one_body_value():
    otp = template(
        [{"type": "BODY", "add_security_recommendation": True}],
        category=MessageTemplate.Category.AUTHENTICATION,
    )

    assert variables.template_slots(otp).body == 1


def test_resolve_value_uses_fallbacks_and_collapses_whitespace():
    contact = Contact(
        name="  Asha \n Rao ",
        phone_e164="+919812345678",
        email="",
        attributes={"city": "Pune", "tier": 3, "meta": {"a": 1}, "blank": "  "},
    )

    assert variables.resolve_value(source("name", "contact_field"), contact) == "Asha Rao"
    assert variables.resolve_value(source("email", "contact_field", "n/a"), contact) == "n/a"
    assert variables.resolve_value(source("tier", "attribute"), contact) == "3"
    assert variables.resolve_value(source("meta", "attribute", "none"), contact) == "none"
    assert variables.resolve_value(source("blank", "attribute"), contact) == ""
    assert variables.resolve_value(source("missing", "attribute"), contact) == ""
    assert variables.resolve_value(source("Diwali\tsale"), contact) == "Diwali sale"


def test_resolve_params_is_none_when_a_value_is_empty():
    contact = Contact(name="Asha", attributes={})
    mapping = {"body": [source("name", "contact_field")], "header": None, "buttons": {}}

    assert variables.resolve_params(mapping, contact) == {
        "body": ["Asha"],
        "header": None,
        "buttons": {},
    }
    mapping["buttons"] = {"0": source("code", "attribute")}
    assert variables.resolve_params(mapping, contact) is None
