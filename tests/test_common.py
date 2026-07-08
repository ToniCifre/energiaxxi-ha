from custom_components.energiaxxi.common import contract_location, slugify
from custom_components.energiaxxi.const import (
    CONF_PRICE_INTERVAL_HOURS,
    CONF_SCAN_INTERVAL_HOURS,
    interval_option,
)


def test_interval_option_prefers_specific_key():
    opts = {CONF_PRICE_INTERVAL_HOURS: 6, CONF_SCAN_INTERVAL_HOURS: 12}
    assert interval_option(opts, CONF_PRICE_INTERVAL_HOURS, 24) == 6


def test_interval_option_falls_back_to_legacy():
    opts = {CONF_SCAN_INTERVAL_HOURS: 9}  # legacy single interval only
    assert interval_option(opts, CONF_PRICE_INTERVAL_HOURS, 24) == 9


def test_interval_option_uses_default():
    assert interval_option({}, CONF_PRICE_INTERVAL_HOURS, 24) == 24


def test_slugify_lowercases_and_replaces():
    assert slugify("130109476822") == "130109476822"
    assert slugify("ES0031-500 ABC") == "es0031_500_abc"
    assert slugify("__A..B__") == "a_b"


def test_contract_location_from_address():
    contract = {
        "contractNumber": "130109476822",
        "physicalAddress": {
            "street": "LLEVANT",
            "number": "22",
            "descriptionMunicipaly": "POLLENÇA",
        },
    }
    assert contract_location(contract) == "LLEVANT 22, POLLENÇA"


def test_contract_location_ignores_placeholder_street_type():
    contract = {
        "contractNumber": "X",
        "physicalAddress": {"street": "LLEVANT", "number": "-", "descriptionCity": "CITY"},
    }
    # number "-" is dropped
    assert contract_location(contract) == "LLEVANT, CITY"


def test_contract_location_falls_back_to_number():
    assert contract_location({"contractNumber": "130109476822"}) == "130109476822"
    assert contract_location({}) == ""
