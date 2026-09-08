"""Foundation contract regressions using temporary copies, with no external access."""

import shutil
from pathlib import Path

import pytest
import yaml

from scripts.validate_config import read_yaml, validate

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repository(tmp_path):
    for folder in ("config", "ops"):
        shutil.copytree(ROOT / folder, tmp_path / folder)
    return tmp_path


def test_repository_contracts():
    validate(ROOT)


@pytest.mark.parametrize(
    ("filename", "field", "value"),
    [
        ("12_kenya_moh.yaml", "categories", ["follow_up"]),
        ("01_rxnorm.yaml", "kmx_levels", ["presentation"]),
        ("01_rxnorm.yaml", "jurisdiction", "UNKNOWN"),
        ("01_rxnorm.yaml", "lane", 2),
        ("01_rxnorm.yaml", "source_id", "athena_extension"),
        ("07_openfda_label.yaml", "rules", True),
        ("01_rxnorm.yaml", "identifiers", []),
    ],
)
def test_reject_invalid_source(repository, filename, field, value):
    path = repository / "config/sources" / filename
    source = read_yaml(path)
    source[field] = value
    path.write_text(yaml.safe_dump(source))
    with pytest.raises(ValueError):
        validate(repository)


def test_reject_missing_source(repository):
    (repository / "config/sources/01_rxnorm.yaml").unlink()
    with pytest.raises(ValueError):
        validate(repository)


def test_reject_wrong_database(repository):
    path = repository / "config/database.yaml"
    config = read_yaml(path)
    config["database"]["name"] = "other_database"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        validate(repository)


def test_reject_duplicate_yaml_key(tmp_path):
    path = tmp_path / "duplicate.yaml"
    path.write_text("status: pending\nstatus: pass\n")
    with pytest.raises(ValueError, match="duplicate YAML key"):
        read_yaml(path)


def test_reject_status_mismatch(repository):
    path = repository / "ops/memory/SOURCE_STATUS.yaml"
    config = read_yaml(path)
    config["sources"]["S01"]["source_id"] = "wrong_source"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        validate(repository)
