import json

import pytest

from name_mapping import load_name_mapping, resolve_name


def test_load_name_mapping_reads_json_file(tmp_path):
    p = tmp_path / "names.json"
    p.write_text(json.dumps({"Артём": "artem.boldyrev"}), encoding="utf-8")

    assert load_name_mapping(p) == {"Артём": "artem.boldyrev"}


def test_load_name_mapping_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_name_mapping(tmp_path / "missing.json")


def test_load_name_mapping_malformed_json_raises(tmp_path):
    p = tmp_path / "names.json"
    p.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        load_name_mapping(p)


def test_load_name_mapping_json_array_raises_value_error(tmp_path):
    p = tmp_path / "names.json"
    p.write_text(json.dumps(["Артём", "artem.boldyrev"]), encoding="utf-8")

    with pytest.raises(ValueError):
        load_name_mapping(p)


def test_resolve_name_exact_match():
    mapping = {"Артём": "artem.boldyrev"}
    assert resolve_name("Артём", mapping) == "artem.boldyrev"


def test_resolve_name_case_insensitive():
    mapping = {"Артём": "artem.boldyrev"}
    assert resolve_name("артём", mapping) == "artem.boldyrev"


def test_resolve_name_not_found_returns_none():
    mapping = {"Артём": "artem.boldyrev"}
    assert resolve_name("Пётр", mapping) is None
