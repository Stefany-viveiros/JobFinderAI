import os
import subprocess
import sys

from scripts.preflight_release import safe_database_label


def test_safe_database_label_never_exposes_credentials():
    label = safe_database_label(
        "postgresql+psycopg://private_user:super-secret@db.example.com:5432/jobfinder"
    )
    assert label == "postgresql+psycopg://db.example.com/jobfinder"
    assert "private_user" not in label
    assert "super-secret" not in label


def test_preflight_refuses_to_guess_database_when_url_is_missing():
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "scripts/preflight_release.py"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 2
    assert '"status": "blocked"' in result.stdout
    assert "mutations_performed" in result.stdout
