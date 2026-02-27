# Pipeline Manager

A local render pipeline management tool for AI-generated media — built with Python, Flask, and SQLite. No cloud accounts, no subscriptions, no data leaving your machine.

![Dashboard](docs/assets/screenshot-dashboard.png)

## What it does

Pipeline Manager tracks every stage of an AI render workflow, from concept through to fully tagged, publish-ready media:

- **Archetypes & Characters** — build a concept library with splash images, subtype classification (Concept vs Meta), and tag-based organisation
- **Ingredients** — define reusable animation building blocks (actions, motions, emotions, styles) with optional short codes and compatibility rules
- **Output Types** — specify what ingredient categories each deliverable format requires
- **Job Builder** — deliberately combine a character with ingredients to create a planned render job, or use the Ideation Mixer on the dashboard to roll random combinations
- **Render Jobs** — track status through planned → in progress → rendered → complete
- **Media Library** — link rendered files to jobs; metadata (title, tags, SEO fields, prompt used) pre-populates from the job so importing is fast
- **Top Layer Media** — composite clips that link multiple render jobs; aggregates their metadata with one click
- **Project Journal** — write and queue prompts, allocate them to projects, copy to clipboard in one click with status tracking (pending → collected → done → flagged)
- **Floating Dock** — a native always-on-top tkinter window for use during active render sessions; shows outstanding jobs, prompt queue, and a drag-to-submit media drop zone
- **Pipeline Funnel** — dashboard metric showing combinations possible → planned → rendered → imported → metadata complete
- **Compatibility Rules** — whitelist/blacklist ingredient combinations
- **Data Manager** — full JSON export/import for backup and version upgrades

## Quick start

**Requirements:** Python 3.8+ with "Add to PATH" ticked during install. That's it.

```
1. Download and unzip the latest release
2. Double-click setup.bat        (first time only — installs Flask)
3. Double-click run.bat          (starts the server)
4. Open http://localhost:5000    (in any browser)
```

To open the floating dock alongside your render software:
```
Double-click dock_launch.bat    (requires the server to be running)
```

## Suggested setup order

1. **Archetypes** — define your character concept templates
2. **Characters** — create specific characters, link to archetypes
3. **Ingredients** → Categories first, then items within each category
4. **Output Types** — define your deliverable formats and which ingredient categories they require
5. **Job Builder** — start planning render jobs
6. **Projects + Journal** — write and queue your prompts, group jobs into campaigns

## Upgrading between versions

1. Go to **Data Manager** (`/data`) and click **Download Export JSON** — save this file
2. Unzip the new version into a fresh folder
3. Run `setup.bat`, then `run.bat`
4. Go to `/data` and import your backup JSON
5. Copy your `static/images/` folder across if you have splash images

## Architecture

| File | Purpose |
|------|---------|
| `app.py` | Flask application — all routes and API endpoints |
| `database.py` | SQLite schema, connection helper, migration functions |
| `dock.pyw` | Native tkinter floating dock (no console window) |
| `templates/` | Jinja2 HTML templates |
| `static/images/` | Uploaded splash images for characters/archetypes |
| `pipeline.db` | SQLite database — created automatically on first run |

## Tech stack

- **Backend:** Flask (Python)
- **Database:** SQLite via the Python standard library
- **Frontend:** Tailwind CSS via CDN, vanilla JS
- **Dock:** tkinter (ships with Python — no extra install)
- **Platform:** Windows (bat files), should run on Mac/Linux with minor adjustments

## Roadmap

- [ ] LLM integration for prompt generation and refinement
- [ ] Direct API connection to SaaS render servers (submit jobs, pull media automatically)
- [ ] Batch metadata editing view
- [ ] Timeline view of render job progress across a project

## License

MIT — do whatever you want with it.
