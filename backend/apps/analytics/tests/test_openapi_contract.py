"""The generated schema carries the analytics contract names (docs/contracts/analytics.md)."""

import pytest
from drf_spectacular.generators import SchemaGenerator

CONTRACT_COMPONENTS = {
    "AnalyticsRange",
    "AnalyticsOverview",
    "AnalyticsTotals",
    "AnalyticsMessages",
    "AnalyticsMessagePoint",
    "AnalyticsSourceRow",
    "AnalyticsCategoryRow",
    "AnalyticsFailureRow",
    "AnalyticsTemplates",
    "AnalyticsTemplateRow",
    "AnalyticsCampaigns",
    "AnalyticsCampaignRow",
    "AnalyticsTeam",
    "AnalyticsTeamRow",
    "AnalyticsCommerce",
    "AnalyticsCommercePoint",
    "AnalyticsOrderStatusRow",
    "AnalyticsPaymentMethodRow",
    "AnalyticsProductRow",
}

OPERATIONS = {
    f"/api/v1/analytics/{name}/": f"analytics_{name}_retrieve"
    for name in ("overview", "messages", "templates", "campaigns", "team", "commerce", "export")
}


@pytest.fixture(scope="module")
def schema():
    return SchemaGenerator().get_schema(request=None, public=True)


def ref(name: str) -> str:
    return f"#/components/schemas/{name}"


def test_components_exist(schema):
    missing = CONTRACT_COMPONENTS - set(schema["components"]["schemas"])
    assert not missing, sorted(missing)


def test_operations_are_gets(schema):
    for path, operation_id in OPERATIONS.items():
        assert set(schema["paths"][path]) == {"get"}, path
        assert schema["paths"][path]["get"]["operationId"] == operation_id


def test_enums_reuse_contract_names(schema):
    components = schema["components"]["schemas"]
    assert components["AnalyticsPaymentMethodEnum"]["enum"] == ["online", "cod"]
    assert components["AnalyticsMessageSourceEnum"]["enum"] == [
        "inbox",
        "campaign",
        "automation",
        "api",
        "commerce",
    ]
    status_row = components["AnalyticsOrderStatusRow"]["properties"]["status"]
    assert status_row["$ref"] == ref("OrderStatusEnum")
    campaign_row = components["AnalyticsCampaignRow"]["properties"]["status"]
    assert campaign_row["$ref"] == ref("CampaignStatusEnum")
    method = components["AnalyticsPaymentMethodRow"]["properties"]["payment_method"]
    assert {item["$ref"] for item in method["oneOf"]} == {
        ref("AnalyticsPaymentMethodEnum"),
        ref("BlankEnum"),
    }


def test_rates_are_nullable_decimal_strings(schema):
    rate = schema["components"]["schemas"]["AnalyticsTotals"]["properties"]["delivery_rate"]
    assert rate["type"] == "string"
    assert rate["format"] == "decimal"
    assert rate["nullable"] is True
