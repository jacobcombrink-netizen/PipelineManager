import sqlite3

DATABASE = 'pipeline.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS archetypes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            subtype TEXT DEFAULT 'concept',
            description TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            archetype_id INTEGER REFERENCES archetypes(id),
            description TEXT DEFAULT '',
            visual_notes TEXT DEFAULT '',
            status TEXT DEFAULT 'concept',
            tags TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ingredient_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER REFERENCES ingredient_categories(id),
            code TEXT DEFAULT '',
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS output_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS output_type_requirements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            output_type_id INTEGER REFERENCES output_types(id),
            category_id INTEGER REFERENCES ingredient_categories(id)
        );

        CREATE TABLE IF NOT EXISTS render_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            character_id INTEGER REFERENCES characters(id),
            output_type_id INTEGER REFERENCES output_types(id),
            status TEXT DEFAULT 'planned',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS render_job_ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER REFERENCES render_jobs(id),
            ingredient_id INTEGER REFERENCES ingredients(id)
        );

        CREATE TABLE IF NOT EXISTS media_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER REFERENCES render_jobs(id),
            character_id INTEGER REFERENCES characters(id),
            output_type_id INTEGER REFERENCES output_types(id),
            file_path TEXT DEFAULT '',
            title TEXT DEFAULT '',
            description TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            seo_title TEXT DEFAULT '',
            seo_description TEXT DEFAULT '',
            quality_status TEXT DEFAULT 'unreviewed',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ingredient_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_type TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_ingredient_id INTEGER REFERENCES ingredients(id),
            source_category_id INTEGER REFERENCES ingredient_categories(id),
            target_type TEXT NOT NULL,
            target_ingredient_id INTEGER REFERENCES ingredients(id),
            target_category_id INTEGER REFERENCES ingredient_categories(id),
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS top_layer_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT '',
            file_path TEXT DEFAULT '',
            description TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            seo_title TEXT DEFAULT '',
            seo_description TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS top_layer_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            top_layer_id INTEGER REFERENCES top_layer_media(id),
            job_id INTEGER REFERENCES render_jobs(id)
        );
    ''')
    conn.commit()
    conn.close()

def migrate_db():
    """Run safe migrations for existing databases."""
    conn = get_db()
    migrations = [
        "ALTER TABLE archetypes ADD COLUMN subtype TEXT DEFAULT 'concept'",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
            conn.commit()
        except Exception:
            pass  # Column/table already exists
    conn.close()


def migrate_db_v2():
    """Add image_path columns to archetypes and characters."""
    conn = get_db()
    migrations = [
        "ALTER TABLE archetypes ADD COLUMN image_path TEXT DEFAULT ''",
        "ALTER TABLE characters ADD COLUMN image_path TEXT DEFAULT ''",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
            conn.commit()
        except Exception:
            pass
    conn.close()


def migrate_db_v3():
    """Add projects, prompts, prompt field on media_assets."""
    conn = get_db()
    migrations = [
        """CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS project_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id),
            job_id INTEGER REFERENCES render_jobs(id)
        )""",
        """CREATE TABLE IF NOT EXISTS prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id),
            job_id INTEGER REFERENCES render_jobs(id),
            text TEXT NOT NULL,
            label TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        "ALTER TABLE media_assets ADD COLUMN prompt TEXT DEFAULT ''",
        """CREATE TABLE IF NOT EXISTS dock_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot INTEGER NOT NULL,
            label TEXT DEFAULT '',
            url TEXT DEFAULT ''
        )""",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
            conn.commit()
        except Exception:
            pass
    # Seed default dock config if empty
    count = conn.execute('SELECT COUNT(*) FROM dock_config').fetchone()[0]
    if count == 0:
        defaults = [
            (1, 'Job Builder', '/jobs/builder'),
            (2, 'Render Jobs', '/jobs'),
            (3, 'Media Library', '/media'),
            (4, 'Journal', '/journal'),
            (5, 'Dashboard', '/'),
        ]
        for slot, label, url in defaults:
            conn.execute('INSERT INTO dock_config (slot, label, url) VALUES (?,?,?)', [slot, label, url])
        conn.commit()
    conn.close()
