from pathlib import Path


def test_skill_manifest_exists() -> None:
    manifest = Path(__file__).resolve().parents[1] / "skill.yaml"
    assert manifest.exists()
