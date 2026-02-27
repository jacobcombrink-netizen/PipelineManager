PIPELINE MANAGER — v0.1
========================
A local web app for managing your rendering pipeline.
No internet required. Runs entirely on your machine.


REQUIREMENTS
------------
- Python 3.8 or higher
  Download from: https://www.python.org/downloads/
  IMPORTANT: During install, tick "Add Python to PATH"


FIRST-TIME SETUP
----------------
1. Double-click setup.bat
   This installs Flask (the only dependency).
   You only need to do this once.


RUNNING THE APP
---------------
1. Double-click run.bat
2. Open your browser and go to: http://localhost:5000
3. To stop the server, press Ctrl+C in the black window (or just close it).


YOUR DATA
---------
All data is stored in a file called pipeline.db in this folder.
This is your database — back it up by copying that file.
It is created automatically on first run.


HOW TO USE
----------
Start here and work top-to-bottom in the sidebar:

1. Archetypes
   Add your high-level character concept types.
   e.g. "The Trickster", "The Hero", "The Villain"
   These are templates — characters are built from them.

2. Characters
   Add specific characters, optionally linked to an archetype.
   Include visual notes and prompt cues for your renders.

3. Ingredients
   Create categories first (e.g. Action, Motion, Emotion).
   Then add items within each category (e.g. Running, Slow Zoom, Manic).
   Use codes (A01, M02) if you use a shorthand system.

4. Output Types
   Define what kinds of deliverables you produce (e.g. Promo Clip, Loop).
   Link ingredient categories as requirements for each output type.

5. Render Jobs
   Log planned and completed render work.
   Track status: Planned → In Progress → Complete.
   Update status inline from the dropdown in the table.

6. Media Library
   Import your finished renders with rich metadata:
   - File path to the render on your hard drive
   - Content description and tags
   - SEO-ready title and description for fast posting
   - Mark assets as Approved, Rejected, or Unreviewed


FUTURE PHASES (planned)
-----------------------
- Untested combination finder (which Action+Motion hasn't been tried for Character X?)
- Inline media preview (image/video thumbnail from file path)
- Bulk import
- Export to CSV or JSON
- Character campaign planner


SUPPORT
-------
This app was built to evolve. All data stays local in pipeline.db.
To add new columns or tables in future, the schema can be updated
without losing existing data.
