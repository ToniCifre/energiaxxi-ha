import re


def slugify(value):
    return re.sub(r'[^a-z0-9_]+', '_', value.lower()).strip('_')


def contract_location(contract: dict) -> str:
    """Human-readable location for a contract, falling back to its number."""
    addr = contract.get("physicalAddress") or {}
    street = " ".join(
        part for part in (addr.get("street"), addr.get("number"))
        if part and part != "-"
    ).strip()
    city = addr.get("descriptionMunicipaly") or addr.get("descriptionCity")
    location = ", ".join(part for part in (street, city) if part)
    return location or str(contract.get("contractNumber", "")).strip()
