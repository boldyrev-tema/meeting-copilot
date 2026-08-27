import pytest
from credentials import load_credential


def test_load_credential_reads_matching_key(tmp_path):
    p = tmp_path / "creds.env"
    p.write_text("FOO=bar\nBAZ=qux\n")
    assert load_credential(str(p), "BAZ") == "qux"


def test_load_credential_missing_key_raises_value_error(tmp_path):
    p = tmp_path / "creds.env"
    p.write_text("FOO=bar\n")
    with pytest.raises(ValueError):
        load_credential(str(p), "MISSING")


def test_load_credential_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_credential(str(tmp_path / "missing.env"), "FOO")
