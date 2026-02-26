from app.auth import is_password_length_valid, hash_password, verify_password


def test_password_within_limit():
    """128 chars should be accepted."""
    assert is_password_length_valid("a" * 128) is True


def test_password_over_limit():
    """129 chars should be rejected."""
    assert is_password_length_valid("a" * 129) is False


def test_unicode_password_within_limit():
    """Unicode chars count as 1 char each, so 128 emoji is fine."""
    assert is_password_length_valid("🚀" * 128) is True


def test_unicode_password_over_limit():
    assert is_password_length_valid("🚀" * 129) is False


def test_argon2_hash_and_verify():
    """Ensure argon2 hash is produced and verifiable."""
    pw = "testPassword!123"
    hashed = hash_password(pw)
    assert hashed.startswith("$argon2"), f"Expected argon2 hash, got: {hashed[:20]}"
    assert verify_password(pw, hashed) is True
    assert verify_password("wrong", hashed) is False
