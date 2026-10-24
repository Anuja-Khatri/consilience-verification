import json, glob
from pathlib import Path
SPRINT = Path(__file__).resolve().parent.parent


def test_a3_dossiers_schema_valid():
    import jsonschema
    schema = json.loads((SPRINT / "results" / "a3_dossier.schema.json").read_text())
    files = glob.glob(str(SPRINT / "results" / "a3_dossiers" / "*.json"))
    assert len(files) == 21  # 14 IIT×GNWT + 7 GNWT×CEMI
    for f in files:
        jsonschema.validate(json.loads(Path(f).read_text()), schema)
    # beyond-key dossiers exist and status is a valid enum
    statuses = {json.loads(Path(f).read_text())["status"] for f in files}
    assert statuses <= {"clean", "flagged", "corrected"}


def test_a3_corrections_file_exists():
    assert (SPRINT / "docs" / "corrections.md").exists()
