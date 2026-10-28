import os
import sqlite3
import subprocess
import sys


def test_legacy_database_is_migrated_without_losing_data(tmp_path):
    """Banco no formato antigo (sem dedupe_key/level) é migrado, com backup e dados preservados."""
    path = tmp_path / "legacy.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE jobs (id INTEGER PRIMARY KEY, source VARCHAR(80), source_id VARCHAR(240), title VARCHAR(300),
          company VARCHAR(200), description TEXT, location VARCHAR(200), modality VARCHAR(50), job_type VARCHAR(80),
          published_at VARCHAR(80), url TEXT UNIQUE, compatibility FLOAT, match_reasons TEXT, missing_reasons TEXT,
          is_favorite BOOLEAN, is_archived BOOLEAN, created_at DATETIME);
        INSERT INTO jobs (id,source,title,company,description,url,compatibility,is_favorite,is_archived)
          VALUES (1,'Remotive','Desenvolvedor Python Júnior','ACME','',  'https://a.test/1', 55, 1, 0);
    """)
    con.commit(); con.close()
    env = {**os.environ, "JOBFINDER_DB_PATH": str(path)}
    for _ in range(2):  # idempotente
        subprocess.run([sys.executable, "-c", "from jobfinder.db import init_db; init_db()"], check=True, env=env)
    con = sqlite3.connect(path)
    row = con.execute("SELECT title, compatibility, is_favorite, level, dedupe_key FROM jobs").fetchone()
    assert row[:3] == ("Desenvolvedor Python Júnior", 55.0, 1)
    assert row[3] == "junior" and row[4] == "desenvolvedor python junior|acme"
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"agent_settings", "application_attempts"} <= tables
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1  # backup feito uma única vez
