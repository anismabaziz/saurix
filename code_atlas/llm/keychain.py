from __future__ import annotations

SERVICE_NAME = "code-atlas"


def save_api_key(provider: str, api_key: str) -> bool:
    keyring = _load_keyring()
    if keyring is None:
        return False
    keyring.set_password(SERVICE_NAME, provider, api_key)
    return True


def load_api_key(provider: str) -> str | None:
    keyring = _load_keyring()
    if keyring is None:
        return None
    value = keyring.get_password(SERVICE_NAME, provider)
    if not value:
        return None
    return value.strip() or None


def _load_keyring():
    try:
        import keyring

        return keyring
    except Exception:
        return None
