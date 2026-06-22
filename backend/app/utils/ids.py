import secrets


def generate_id(prefix: str, nbytes: int = 4) -> str:
    return f"{prefix}_{secrets.token_hex(nbytes)}"
