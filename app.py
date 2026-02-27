from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from database import init_db, migrate_db, migrate_db_v2, migrate_db_v3, get_db
import json, os, uuid, io
from datetime import datetime
from werkzeug.utils import secure_filename
import base64, re

app = Flask(__name__)
app.secret_key = 'pipeline-manager-dev-key'

IMAGES_DIR = os.path.join(os.path.dirname(__file__), 'static', 'images')
os.makedirs(IMAGES_DIR, exist_ok=True)

with app.app_context():
    init_db()
    migrate_db()
    migrate_db_v2()
    migrate_db_v3()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def combo_stats(db):
    output_types = db.execute('SELECT * FROM output_types').fetchall()
    char_count = db.execute("SELECT COUNT(*) FROM characters WHERE status != 'retired'").fetchone()[0]
    total_possible = 0
    for ot in output_types:
        reqs = db.execute('SELECT category_id FROM output_type_requirements WHERE output_type_id=?', [ot['id']]).fetchall()
        if not reqs:
            continue
        combos = char_count
        for req in reqs:
            count = db.execute('SELECT COUNT(*) FROM ingredients WHERE category_id=?', [req['category_id']]).fetchone()[0]
            combos *= max(count, 1)
        total_possible += combos
    total_planned = db.execute('SELECT COUNT(*) FROM render_jobs').fetchone()[0]
    total_rendered = db.execute("SELECT COUNT(*) FROM render_jobs WHERE status IN ('rendered','complete')").fetchone()[0]
    total_imported = db.execute('SELECT COUNT(DISTINCT job_id) FROM media_assets WHERE job_id IS NOT NULL').fetchone()[0]
    total_meta_complete = db.execute("""
        SELECT COUNT(*) FROM media_assets
        WHERE job_id IS NOT NULL AND title != '' AND description != ''
        AND tags != '' AND seo_title != '' AND seo_description != ''
    """).fetchone()[0]
    return {
        'total_possible': total_possible, 'total_planned': total_planned,
        'total_rendered': total_rendered, 'total_imported': total_imported,
        'total_meta_complete': total_meta_complete,
    }


# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    db = get_db()
    stats = {
        'archetypes':   db.execute('SELECT COUNT(*) FROM archetypes').fetchone()[0],
        'characters':   db.execute('SELECT COUNT(*) FROM characters').fetchone()[0],
        'ingredients':  db.execute('SELECT COUNT(*) FROM ingredients').fetchone()[0],
        'output_types': db.execute('SELECT COUNT(*) FROM output_types').fetchone()[0],
        'media_total':  db.execute('SELECT COUNT(*) FROM media_assets').fetchone()[0],
        'top_layer':    db.execute('SELECT COUNT(*) FROM top_layer_media').fetchone()[0],
    }
    funnel = combo_stats(db)
    recent_media = db.execute('''
        SELECT ma.*, c.name as character_name, ot.name as output_type_name
        FROM media_assets ma LEFT JOIN characters c ON ma.character_id=c.id
        LEFT JOIN output_types ot ON ma.output_type_id=ot.id
        ORDER BY ma.created_at DESC LIMIT 6
    ''').fetchall()
    recent_jobs = db.execute('''
        SELECT rj.*, c.name as character_name, ot.name as output_type_name
        FROM render_jobs rj LEFT JOIN characters c ON rj.character_id=c.id
        LEFT JOIN output_types ot ON rj.output_type_id=ot.id
        ORDER BY rj.created_at DESC LIMIT 5
    ''').fetchall()
    characters_list = db.execute("SELECT * FROM characters WHERE status!='retired' ORDER BY name").fetchall()
    output_types_list = db.execute('SELECT * FROM output_types ORDER BY name').fetchall()
    db.close()
    return render_template('index.html', stats=stats, funnel=funnel,
                           recent_media=recent_media, recent_jobs=recent_jobs,
                           characters=characters_list, output_types=output_types_list)


# ─── API ──────────────────────────────────────────────────────────────────────

@app.route('/api/random-combo')
def api_random_combo():
    db = get_db()
    lock_char = request.args.get('char_id')
    lock_ot = request.args.get('ot_id')
    lock_ings = request.args.getlist('ing_id')
    char = db.execute('SELECT * FROM characters WHERE id=?', [lock_char]).fetchone() if lock_char else \
           db.execute("SELECT * FROM characters WHERE status!='retired' ORDER BY RANDOM() LIMIT 1").fetchone()
    ot = db.execute('SELECT * FROM output_types WHERE id=?', [lock_ot]).fetchone() if lock_ot else \
         db.execute('SELECT * FROM output_types ORDER BY RANDOM() LIMIT 1').fetchone()
    result = {'character': dict(char) if char else None, 'output_type': dict(ot) if ot else None, 'ingredients': []}
    if ot:
        reqs = db.execute('''SELECT ic.* FROM output_type_requirements otr
            JOIN ingredient_categories ic ON otr.category_id=ic.id
            WHERE otr.output_type_id=? ORDER BY ic.name''', [ot['id']]).fetchall()
        for req in reqs:
            locked_ing = None
            if lock_ings:
                locked_ing = db.execute(
                    'SELECT * FROM ingredients WHERE id IN ({}) AND category_id=?'.format(','.join(['?']*len(lock_ings))),
                    list(lock_ings)+[req['id']]).fetchone()
            ing = locked_ing or db.execute('SELECT * FROM ingredients WHERE category_id=? ORDER BY RANDOM() LIMIT 1', [req['id']]).fetchone()
            result['ingredients'].append({'category': dict(req), 'ingredient': dict(ing) if ing else None})
    db.close()
    return jsonify(result)

@app.route('/api/job-data/<int:job_id>')
def api_job_data(job_id):
    db = get_db()
    job = db.execute('''SELECT rj.*, c.name as character_name, c.description as char_desc,
        c.tags as char_tags, ot.name as output_type_name
        FROM render_jobs rj LEFT JOIN characters c ON rj.character_id=c.id
        LEFT JOIN output_types ot ON rj.output_type_id=ot.id WHERE rj.id=?''', [job_id]).fetchone()
    if not job:
        return jsonify({'error': 'Not found'}), 404
    ings = db.execute('''SELECT i.name, i.code, ic.name as category_name
        FROM render_job_ingredients rji JOIN ingredients i ON rji.ingredient_id=i.id
        JOIN ingredient_categories ic ON i.category_id=ic.id WHERE rji.job_id=? ORDER BY ic.name''', [job_id]).fetchall()
    ing_list = [dict(i) for i in ings]
    ing_names = ', '.join(i['name'] for i in ing_list)
    auto_title = job['character_name'] or ''
    if ing_names: auto_title += (' — ' + ing_names) if auto_title else ing_names
    auto_tags = ''
    if job['character_name']: auto_tags = job['character_name'].lower().replace(' ', ',')
    if job['char_tags']: auto_tags += ',' + job['char_tags']
    if ing_names: auto_tags += ',' + ','.join(i['name'].lower() for i in ing_list)
    db.close()
    return jsonify({'job': dict(job), 'ingredients': ing_list, 'auto_title': auto_title,
                    'auto_tags': auto_tags, 'character_id': job['character_id'], 'output_type_id': job['output_type_id']})

@app.route('/api/output-type-requirements/<int:ot_id>')
def api_ot_requirements(ot_id):
    db = get_db()
    reqs = db.execute('''SELECT ic.* FROM output_type_requirements otr
        JOIN ingredient_categories ic ON otr.category_id=ic.id
        WHERE otr.output_type_id=? ORDER BY ic.name''', [ot_id]).fetchall()
    result = []
    for req in reqs:
        ings = db.execute('SELECT * FROM ingredients WHERE category_id=? ORDER BY code, name', [req['id']]).fetchall()
        result.append({'category': dict(req), 'ingredients': [dict(i) for i in ings]})
    db.close()
    return jsonify(result)

@app.route('/api/top-layer-meta/<int:top_id>')
def api_top_layer_meta(top_id):
    db = get_db()
    linked_media = db.execute('''SELECT ma.*, c.name as character_name FROM top_layer_jobs tlj
        JOIN render_jobs rj ON tlj.job_id=rj.id
        LEFT JOIN media_assets ma ON ma.job_id=rj.id
        LEFT JOIN characters c ON ma.character_id=c.id
        WHERE tlj.top_layer_id=? AND ma.id IS NOT NULL''', [top_id]).fetchall()
    all_tags, all_chars, descriptions, seo_parts = set(), set(), [], []
    for m in linked_media:
        if m['tags']:
            for t in m['tags'].split(','):
                if t.strip(): all_tags.add(t.strip())
        if m['character_name']: all_chars.add(m['character_name'])
        if m['description']: descriptions.append(m['description'])
        if m['seo_description']: seo_parts.append(m['seo_description'])
    db.close()
    return jsonify({'tags': ', '.join(sorted(all_tags)), 'characters': ', '.join(sorted(all_chars)),
                    'description': ' | '.join(dict.fromkeys(descriptions))[:1000],
                    'seo_description': ' '.join(dict.fromkeys(seo_parts))[:500]})


# ─── Archetypes ───────────────────────────────────────────────────────────────

@app.route('/archetypes')
def archetypes():
    db = get_db()
    items = db.execute('''SELECT a.*, COUNT(c.id) as char_count FROM archetypes a
        LEFT JOIN characters c ON c.archetype_id=a.id GROUP BY a.id ORDER BY a.subtype, a.name''').fetchall()
    db.close()
    return render_template('archetypes.html', items=items)

@app.route('/archetypes/add', methods=['POST'])
def add_archetype():
    db = get_db()
    db.execute('INSERT INTO archetypes (name, subtype, description, tags) VALUES (?,?,?,?)',
               [request.form['name'], request.form.get('subtype','concept'), request.form.get('description',''), request.form.get('tags','')])
    db.commit(); db.close(); flash('Archetype added.'); return redirect(url_for('archetypes'))

@app.route('/archetypes/edit/<int:id>', methods=['POST'])
def edit_archetype(id):
    db = get_db()
    db.execute('UPDATE archetypes SET name=?, subtype=?, description=?, tags=?, image_path=? WHERE id=?',
               [request.form['name'], request.form.get('subtype','concept'), request.form.get('description',''), request.form.get('tags',''), request.form.get('image_path',''), id])
    db.commit(); db.close(); flash('Archetype updated.'); return redirect(url_for('archetypes'))

@app.route('/archetypes/delete/<int:id>', methods=['POST'])
def delete_archetype(id):
    db = get_db()
    db.execute('DELETE FROM archetypes WHERE id=?', [id]); db.commit(); db.close()
    flash('Archetype deleted.'); return redirect(url_for('archetypes'))


# ─── Characters ───────────────────────────────────────────────────────────────

@app.route('/characters')
def characters():
    db = get_db()
    items = db.execute('''SELECT c.*, a.name as archetype_name FROM characters c
        LEFT JOIN archetypes a ON c.archetype_id=a.id ORDER BY c.name''').fetchall()
    archetypes_list = db.execute('SELECT * FROM archetypes ORDER BY name').fetchall()
    db.close()
    return render_template('characters.html', items=items, archetypes=archetypes_list)

@app.route('/characters/add', methods=['POST'])
def add_character():
    db = get_db()
    db.execute('INSERT INTO characters (name, archetype_id, description, visual_notes, status, tags) VALUES (?,?,?,?,?,?)',
               [request.form['name'], request.form.get('archetype_id') or None, request.form.get('description',''),
                request.form.get('visual_notes',''), request.form.get('status','concept'), request.form.get('tags','')])
    db.commit(); db.close(); flash('Character added.'); return redirect(url_for('characters'))

@app.route('/characters/edit/<int:id>', methods=['POST'])
def edit_character(id):
    db = get_db()
    db.execute('UPDATE characters SET name=?, archetype_id=?, description=?, visual_notes=?, status=?, tags=?, image_path=? WHERE id=?',
               [request.form['name'], request.form.get('archetype_id') or None, request.form.get('description',''),
                request.form.get('visual_notes',''), request.form.get('status','concept'), request.form.get('tags',''), request.form.get('image_path',''), id])
    db.commit(); db.close(); flash('Character updated.'); return redirect(url_for('characters'))

@app.route('/characters/delete/<int:id>', methods=['POST'])
def delete_character(id):
    db = get_db()
    db.execute('DELETE FROM characters WHERE id=?', [id]); db.commit(); db.close()
    flash('Character deleted.'); return redirect(url_for('characters'))


# ─── Ingredients ──────────────────────────────────────────────────────────────

@app.route('/ingredients')
def ingredients():
    db = get_db()
    categories = db.execute('''SELECT ic.*, COUNT(i.id) as item_count FROM ingredient_categories ic
        LEFT JOIN ingredients i ON i.category_id=ic.id GROUP BY ic.id ORDER BY ic.name''').fetchall()
    items = db.execute('''SELECT i.*, ic.name as category_name FROM ingredients i
        JOIN ingredient_categories ic ON i.category_id=ic.id ORDER BY ic.name, i.code, i.name''').fetchall()
    rules = db.execute('''SELECT r.*, si.name as source_ing_name, sc.name as source_cat_name,
        ti.name as target_ing_name, tc.name as target_cat_name FROM ingredient_rules r
        LEFT JOIN ingredients si ON r.source_ingredient_id=si.id
        LEFT JOIN ingredient_categories sc ON r.source_category_id=sc.id
        LEFT JOIN ingredients ti ON r.target_ingredient_id=ti.id
        LEFT JOIN ingredient_categories tc ON r.target_category_id=tc.id
        ORDER BY r.rule_type, r.id''').fetchall()
    db.close()
    return render_template('ingredients.html', categories=categories, items=items, rules=rules)

@app.route('/ingredients/categories/add', methods=['POST'])
def add_category():
    db = get_db()
    try:
        db.execute('INSERT INTO ingredient_categories (name, description) VALUES (?,?)',
                   [request.form['name'], request.form.get('description','')]); db.commit(); flash('Category added.')
    except: flash('Name already exists.')
    db.close(); return redirect(url_for('ingredients'))

@app.route('/ingredients/categories/edit/<int:id>', methods=['POST'])
def edit_category(id):
    db = get_db()
    try:
        db.execute('UPDATE ingredient_categories SET name=?, description=? WHERE id=?',
                   [request.form['name'], request.form.get('description',''), id]); db.commit(); flash('Category updated.')
    except: flash('Name already taken.')
    db.close(); return redirect(url_for('ingredients'))

@app.route('/ingredients/categories/delete/<int:id>', methods=['POST'])
def delete_category(id):
    db = get_db()
    db.execute('DELETE FROM ingredients WHERE category_id=?', [id])
    db.execute('DELETE FROM ingredient_categories WHERE id=?', [id]); db.commit(); db.close()
    flash('Category deleted.'); return redirect(url_for('ingredients'))

@app.route('/ingredients/add', methods=['POST'])
def add_ingredient():
    db = get_db()
    db.execute('INSERT INTO ingredients (category_id, code, name, description) VALUES (?,?,?,?)',
               [request.form['category_id'], request.form.get('code',''), request.form['name'], request.form.get('description','')]); db.commit(); db.close()
    flash('Ingredient added.'); return redirect(url_for('ingredients'))

@app.route('/ingredients/edit/<int:id>', methods=['POST'])
def edit_ingredient(id):
    db = get_db()
    db.execute('UPDATE ingredients SET category_id=?, code=?, name=?, description=? WHERE id=?',
               [request.form['category_id'], request.form.get('code',''), request.form['name'], request.form.get('description',''), id]); db.commit(); db.close()
    flash('Ingredient updated.'); return redirect(url_for('ingredients'))

@app.route('/ingredients/delete/<int:id>', methods=['POST'])
def delete_ingredient(id):
    db = get_db()
    db.execute('DELETE FROM ingredients WHERE id=?', [id]); db.commit(); db.close()
    return redirect(url_for('ingredients'))

@app.route('/ingredients/rules/add', methods=['POST'])
def add_rule():
    db = get_db()
    f = request.form
    db.execute('''INSERT INTO ingredient_rules (rule_type,source_type,source_ingredient_id,source_category_id,
        target_type,target_ingredient_id,target_category_id,notes) VALUES (?,?,?,?,?,?,?,?)''',
        [f['rule_type'], f['source_type'], f.get('source_ingredient_id') or None, f.get('source_category_id') or None,
         f['target_type'], f.get('target_ingredient_id') or None, f.get('target_category_id') or None, f.get('notes','')])
    db.commit(); db.close(); flash('Rule added.'); return redirect(url_for('ingredients'))

@app.route('/ingredients/rules/delete/<int:id>', methods=['POST'])
def delete_rule(id):
    db = get_db()
    db.execute('DELETE FROM ingredient_rules WHERE id=?', [id]); db.commit(); db.close()
    return redirect(url_for('ingredients'))


# ─── Output Types ─────────────────────────────────────────────────────────────

@app.route('/output-types')
def output_types():
    db = get_db()
    items = db.execute('SELECT * FROM output_types ORDER BY name').fetchall()
    categories = db.execute('SELECT * FROM ingredient_categories ORDER BY name').fetchall()
    requirements = db.execute('''SELECT otr.*, ot.name as output_name, ic.name as category_name
        FROM output_type_requirements otr JOIN output_types ot ON otr.output_type_id=ot.id
        JOIN ingredient_categories ic ON otr.category_id=ic.id ORDER BY ot.name, ic.name''').fetchall()
    db.close()
    return render_template('output_types.html', items=items, categories=categories, requirements=requirements)

@app.route('/output-types/add', methods=['POST'])
def add_output_type():
    db = get_db()
    db.execute('INSERT INTO output_types (name, description) VALUES (?,?)',
               [request.form['name'], request.form.get('description','')]); db.commit(); db.close()
    flash('Output type added.'); return redirect(url_for('output_types'))

@app.route('/output-types/edit/<int:id>', methods=['POST'])
def edit_output_type(id):
    db = get_db()
    db.execute('UPDATE output_types SET name=?, description=? WHERE id=?',
               [request.form['name'], request.form.get('description',''), id]); db.commit(); db.close()
    flash('Output type updated.'); return redirect(url_for('output_types'))

@app.route('/output-types/delete/<int:id>', methods=['POST'])
def delete_output_type(id):
    db = get_db()
    db.execute('DELETE FROM output_type_requirements WHERE output_type_id=?', [id])
    db.execute('DELETE FROM output_types WHERE id=?', [id]); db.commit(); db.close()
    flash('Output type deleted.'); return redirect(url_for('output_types'))

@app.route('/output-types/add-requirement', methods=['POST'])
def add_requirement():
    db = get_db()
    db.execute('INSERT INTO output_type_requirements (output_type_id, category_id) VALUES (?,?)',
               [request.form['output_type_id'], request.form['category_id']]); db.commit(); db.close()
    flash('Requirement added.'); return redirect(url_for('output_types'))

@app.route('/output-types/delete-requirement/<int:id>', methods=['POST'])
def delete_requirement(id):
    db = get_db()
    db.execute('DELETE FROM output_type_requirements WHERE id=?', [id]); db.commit(); db.close()
    return redirect(url_for('output_types'))


# ─── Job Builder ──────────────────────────────────────────────────────────────

@app.route('/jobs/builder')
def job_builder():
    db = get_db()
    characters_list = db.execute("SELECT * FROM characters WHERE status!='retired' ORDER BY name").fetchall()
    output_types_list = db.execute('SELECT * FROM output_types ORDER BY name').fetchall()
    all_categories = db.execute('SELECT * FROM ingredient_categories ORDER BY name').fetchall()
    all_ingredients = db.execute('''SELECT i.*, ic.name as category_name FROM ingredients i
        JOIN ingredient_categories ic ON i.category_id=ic.id ORDER BY ic.name, i.code, i.name''').fetchall()
    db.close()
    return render_template('job_builder.html', characters=characters_list, output_types=output_types_list,
                           all_categories=all_categories, all_ingredients=all_ingredients)

@app.route('/jobs/builder', methods=['POST'])
def create_job_from_builder():
    db = get_db()
    job_id = db.execute('INSERT INTO render_jobs (character_id, output_type_id, status, notes) VALUES (?,?,?,?)',
               [request.form.get('character_id') or None, request.form.get('output_type_id') or None,
                request.form.get('status','planned'), request.form.get('notes','')]).lastrowid
    for ing_id in request.form.getlist('ingredient_ids'):
        if ing_id:
            db.execute('INSERT INTO render_job_ingredients (job_id, ingredient_id) VALUES (?,?)', [job_id, ing_id])
    db.commit(); db.close()
    flash(f'Render job #{job_id} created from builder.')
    return redirect(url_for('jobs'))


# ─── Render Jobs ──────────────────────────────────────────────────────────────

@app.route('/jobs')
def jobs():
    db = get_db()
    status_filter = request.args.get('status', '')
    query = '''SELECT rj.*, c.name as character_name, ot.name as output_type_name FROM render_jobs rj
        LEFT JOIN characters c ON rj.character_id=c.id LEFT JOIN output_types ot ON rj.output_type_id=ot.id'''
    items = db.execute(query + (' WHERE rj.status=?' if status_filter else '') + ' ORDER BY rj.created_at DESC',
                       [status_filter] if status_filter else []).fetchall()
    job_ingredients = {}
    for job in items:
        ings = db.execute('''SELECT i.name, i.code, ic.name as category_name FROM render_job_ingredients rji
            JOIN ingredients i ON rji.ingredient_id=i.id JOIN ingredient_categories ic ON i.category_id=ic.id
            WHERE rji.job_id=?''', [job['id']]).fetchall()
        job_ingredients[job['id']] = ings
    jobs_with_media = set(row[0] for row in db.execute('SELECT DISTINCT job_id FROM media_assets WHERE job_id IS NOT NULL').fetchall())
    characters_list = db.execute("SELECT * FROM characters WHERE status!='retired' ORDER BY name").fetchall()
    output_types_list = db.execute('SELECT * FROM output_types ORDER BY name').fetchall()
    db.close()
    return render_template('jobs.html', items=items, characters=characters_list, output_types=output_types_list,
                           status_filter=status_filter, job_ingredients=job_ingredients, jobs_with_media=jobs_with_media)

@app.route('/jobs/add', methods=['POST'])
def add_job():
    db = get_db()
    db.execute('INSERT INTO render_jobs (character_id, output_type_id, status, notes) VALUES (?,?,?,?)',
               [request.form.get('character_id') or None, request.form.get('output_type_id') or None,
                request.form.get('status','planned'), request.form.get('notes','')]); db.commit(); db.close()
    flash('Job added.'); return redirect(url_for('jobs'))

@app.route('/jobs/edit/<int:id>', methods=['POST'])
def edit_job(id):
    db = get_db()
    db.execute('UPDATE render_jobs SET character_id=?, output_type_id=?, status=?, notes=? WHERE id=?',
               [request.form.get('character_id') or None, request.form.get('output_type_id') or None,
                request.form.get('status','planned'), request.form.get('notes',''), id]); db.commit(); db.close()
    flash('Job updated.'); return redirect(url_for('jobs'))

@app.route('/jobs/update-status/<int:id>', methods=['POST'])
def update_job_status(id):
    db = get_db()
    db.execute('UPDATE render_jobs SET status=? WHERE id=?', [request.form['status'], id]); db.commit(); db.close()
    return redirect(request.referrer or url_for('jobs'))

@app.route('/jobs/delete/<int:id>', methods=['POST'])
def delete_job(id):
    db = get_db()
    db.execute('DELETE FROM render_job_ingredients WHERE job_id=?', [id])
    db.execute('DELETE FROM render_jobs WHERE id=?', [id]); db.commit(); db.close()
    flash('Job deleted.'); return redirect(url_for('jobs'))


# ─── Media Assets ─────────────────────────────────────────────────────────────

@app.route('/media')
def media():
    db = get_db()
    status_filter = request.args.get('status', '')
    char_filter = request.args.get('character_id', '')
    query = '''SELECT ma.*, c.name as character_name, ot.name as output_type_name FROM media_assets ma
        LEFT JOIN characters c ON ma.character_id=c.id LEFT JOIN output_types ot ON ma.output_type_id=ot.id WHERE 1=1'''
    params = []
    if status_filter: query += ' AND ma.quality_status=?'; params.append(status_filter)
    if char_filter: query += ' AND ma.character_id=?'; params.append(char_filter)
    query += ' ORDER BY ma.created_at DESC'
    items = db.execute(query, params).fetchall()
    pending_jobs = db.execute('''SELECT rj.*, c.name as character_name, ot.name as output_type_name FROM render_jobs rj
        LEFT JOIN characters c ON rj.character_id=c.id LEFT JOIN output_types ot ON rj.output_type_id=ot.id
        WHERE rj.id NOT IN (SELECT DISTINCT job_id FROM media_assets WHERE job_id IS NOT NULL)
        AND rj.status IN ('rendered','complete') ORDER BY rj.created_at DESC''').fetchall()
    all_jobs = db.execute('''SELECT rj.*, c.name as character_name, ot.name as output_type_name FROM render_jobs rj
        LEFT JOIN characters c ON rj.character_id=c.id LEFT JOIN output_types ot ON rj.output_type_id=ot.id
        ORDER BY rj.created_at DESC''').fetchall()
    characters_list = db.execute('SELECT * FROM characters ORDER BY name').fetchall()
    output_types_list = db.execute('SELECT * FROM output_types ORDER BY name').fetchall()
    db.close()
    return render_template('media.html', items=items, characters=characters_list, output_types=output_types_list,
                           status_filter=status_filter, char_filter=char_filter, pending_jobs=pending_jobs, all_jobs=all_jobs)

@app.route('/media/add', methods=['POST'])
def add_media():
    db = get_db()
    db.execute('''INSERT INTO media_assets (job_id,character_id,output_type_id,file_path,title,description,
        tags,seo_title,seo_description,quality_status,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
        [request.form.get('job_id') or None, request.form.get('character_id') or None,
         request.form.get('output_type_id') or None, request.form.get('file_path',''),
         request.form.get('title',''), request.form.get('description',''), request.form.get('tags',''),
         request.form.get('seo_title',''), request.form.get('seo_description',''),
         request.form.get('quality_status','unreviewed'), request.form.get('notes','')]); db.commit(); db.close()
    flash('Media asset imported.'); return redirect(url_for('media'))

@app.route('/media/edit/<int:id>', methods=['POST'])
def edit_media(id):
    db = get_db()
    db.execute('UPDATE media_assets SET title=?,file_path=?,description=?,tags=?,seo_title=?,seo_description=?,quality_status=?,notes=?,prompt=? WHERE id=?',
        [request.form.get('title',''), request.form.get('file_path',''), request.form.get('description',''),
         request.form.get('tags',''), request.form.get('seo_title',''), request.form.get('seo_description',''),
         request.form.get('quality_status','unreviewed'), request.form.get('notes',''), request.form.get('prompt',''), id]); db.commit(); db.close()
    flash('Asset updated.'); return redirect(url_for('media'))

@app.route('/media/update-status/<int:id>', methods=['POST'])
def update_media_status(id):
    db = get_db()
    db.execute('UPDATE media_assets SET quality_status=? WHERE id=?', [request.form['quality_status'], id]); db.commit(); db.close()
    return redirect(request.referrer or url_for('media'))

@app.route('/media/delete/<int:id>', methods=['POST'])
def delete_media(id):
    db = get_db()
    db.execute('DELETE FROM media_assets WHERE id=?', [id]); db.commit(); db.close()
    flash('Asset deleted.'); return redirect(url_for('media'))


# ─── Top Layer Media ──────────────────────────────────────────────────────────

@app.route('/top-layer')
def top_layer():
    db = get_db()
    items = db.execute('SELECT * FROM top_layer_media ORDER BY created_at DESC').fetchall()
    item_jobs = {}
    for item in items:
        linked = db.execute('''SELECT tlj.id as link_id, rj.*, c.name as character_name, ot.name as output_type_name,
            ma.title as media_title, ma.tags as media_tags, ma.description as media_desc,
            ma.seo_title as media_seo_title, ma.seo_description as media_seo_desc, ma.quality_status
            FROM top_layer_jobs tlj JOIN render_jobs rj ON tlj.job_id=rj.id
            LEFT JOIN characters c ON rj.character_id=c.id LEFT JOIN output_types ot ON rj.output_type_id=ot.id
            LEFT JOIN media_assets ma ON ma.job_id=rj.id WHERE tlj.top_layer_id=?''', [item['id']]).fetchall()
        item_jobs[item['id']] = linked
    all_jobs = db.execute('''SELECT rj.*, c.name as character_name, ot.name as output_type_name FROM render_jobs rj
        LEFT JOIN characters c ON rj.character_id=c.id LEFT JOIN output_types ot ON rj.output_type_id=ot.id
        ORDER BY rj.created_at DESC''').fetchall()
    db.close()
    return render_template('top_layer.html', items=items, item_jobs=item_jobs, all_jobs=all_jobs)

@app.route('/top-layer/add', methods=['POST'])
def add_top_layer():
    db = get_db()
    db.execute('INSERT INTO top_layer_media (title, file_path, notes) VALUES (?,?,?)',
               [request.form.get('title',''), request.form.get('file_path',''), request.form.get('notes','')]); db.commit(); db.close()
    flash('Top layer clip added.'); return redirect(url_for('top_layer'))

@app.route('/top-layer/edit/<int:id>', methods=['POST'])
def edit_top_layer(id):
    db = get_db()
    db.execute('''UPDATE top_layer_media SET title=?,file_path=?,description=?,tags=?,seo_title=?,seo_description=?,notes=? WHERE id=?''',
               [request.form.get('title',''), request.form.get('file_path',''), request.form.get('description',''),
                request.form.get('tags',''), request.form.get('seo_title',''), request.form.get('seo_description',''),
                request.form.get('notes',''), id]); db.commit(); db.close()
    flash('Clip updated.'); return redirect(url_for('top_layer'))

@app.route('/top-layer/delete/<int:id>', methods=['POST'])
def delete_top_layer(id):
    db = get_db()
    db.execute('DELETE FROM top_layer_jobs WHERE top_layer_id=?', [id])
    db.execute('DELETE FROM top_layer_media WHERE id=?', [id]); db.commit(); db.close()
    flash('Clip deleted.'); return redirect(url_for('top_layer'))

@app.route('/top-layer/link-job/<int:top_id>', methods=['POST'])
def link_top_layer_job(top_id):
    db = get_db()
    job_id = request.form.get('job_id')
    if job_id:
        existing = db.execute('SELECT id FROM top_layer_jobs WHERE top_layer_id=? AND job_id=?', [top_id, job_id]).fetchone()
        if not existing:
            db.execute('INSERT INTO top_layer_jobs (top_layer_id, job_id) VALUES (?,?)', [top_id, job_id]); db.commit()
    db.close(); return redirect(url_for('top_layer'))

@app.route('/top-layer/unlink-job/<int:id>', methods=['POST'])
def unlink_top_layer_job(id):
    db = get_db()
    db.execute('DELETE FROM top_layer_jobs WHERE id=?', [id]); db.commit(); db.close()
    return redirect(url_for('top_layer'))



# ─── Image Upload ─────────────────────────────────────────────────────────────

@app.route('/upload-image', methods=['POST'])
def upload_image():
    """Accept file upload or base64 paste, save to static/images, return filename."""
    filename = None

    # Base64 paste (from clipboard)
    if request.is_json:
        data = request.get_json()
        b64 = data.get('image_b64', '')
        # Strip data URI prefix if present
        if ',' in b64:
            b64 = b64.split(',', 1)[1]
        ext = 'png'
        if 'jpeg' in data.get('mime', ''):
            ext = 'jpg'
        filename = f"{uuid.uuid4().hex}.{ext}"
        path = os.path.join(IMAGES_DIR, filename)
        with open(path, 'wb') as f:
            f.write(base64.b64decode(b64))

    # File drag-drop
    elif 'image' in request.files:
        file = request.files['image']
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'png'
        if ext not in ('png', 'jpg', 'jpeg', 'gif', 'webp'):
            return jsonify({'error': 'Unsupported format'}), 400
        filename = f"{uuid.uuid4().hex}.{ext}"
        file.save(os.path.join(IMAGES_DIR, filename))

    if filename:
        return jsonify({'filename': filename, 'url': f'/static/images/{filename}'})
    return jsonify({'error': 'No image received'}), 400


# ─── Export / Import ──────────────────────────────────────────────────────────

@app.route('/data')
def data_manager():
    db = get_db()
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
    counts = {t: db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in tables}
    db.close()
    return render_template('data_manager.html', tables=tables, counts=counts)


@app.route('/export')
def export_data():
    db = get_db()
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
    export = {
        'exported_at': datetime.utcnow().isoformat(),
        'version': '0.2',
        'tables': {}
    }
    for table in tables:
        rows = db.execute(f'SELECT * FROM {table}').fetchall()
        export['tables'][table] = [dict(r) for r in rows]
    db.close()
    buf = io.BytesIO(json.dumps(export, indent=2).encode('utf-8'))
    buf.seek(0)
    filename = f"pipeline_export_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.json"
    return send_file(buf, mimetype='application/json', as_attachment=True, download_name=filename)


@app.route('/import', methods=['POST'])
def import_data():
    if 'file' not in request.files:
        flash('No file selected.')
        return redirect(url_for('data_manager'))
    file = request.files['file']
    if not file.filename.endswith('.json'):
        flash('Please upload a .json export file.')
        return redirect(url_for('data_manager'))

    try:
        data = json.loads(file.read().decode('utf-8'))
    except Exception as e:
        flash(f'Could not parse file: {e}')
        return redirect(url_for('data_manager'))

    tables = data.get('tables', {})
    db = get_db()

    # Import order respects foreign keys
    import_order = [
        'archetypes', 'characters', 'ingredient_categories', 'ingredients',
        'output_types', 'output_type_requirements', 'render_jobs',
        'render_job_ingredients', 'media_assets', 'ingredient_rules',
        'top_layer_media', 'top_layer_jobs'
    ]

    total_imported = 0
    total_skipped = 0

    for table in import_order:
        rows = tables.get(table, [])
        if not rows:
            continue
        # Get existing columns
        cols_info = db.execute(f'PRAGMA table_info({table})').fetchall()
        col_names = [c[1] for c in cols_info]

        for row in rows:
            # Only insert columns that exist in current schema
            filtered = {k: v for k, v in row.items() if k in col_names}
            if not filtered:
                continue
            # Skip if record with this ID already exists
            existing = db.execute(f"SELECT id FROM {table} WHERE id=?", [filtered.get('id')]).fetchone()
            if existing:
                total_skipped += 1
                continue
            placeholders = ', '.join(['?'] * len(filtered))
            cols = ', '.join(filtered.keys())
            try:
                db.execute(f'INSERT INTO {table} ({cols}) VALUES ({placeholders})', list(filtered.values()))
                total_imported += 1
            except Exception:
                total_skipped += 1

    db.commit()
    db.close()
    flash(f'Import complete: {total_imported} records added, {total_skipped} skipped (already existed).')
    return redirect(url_for('data_manager'))


@app.route('/archetypes/set-image/<int:id>', methods=['POST'])
def set_archetype_image(id):
    db = get_db()
    db.execute('UPDATE archetypes SET image_path=? WHERE id=?', [request.form.get('image_path',''), id])
    db.commit(); db.close()
    return redirect(url_for('archetypes'))

@app.route('/characters/set-image/<int:id>', methods=['POST'])
def set_character_image(id):
    db = get_db()
    db.execute('UPDATE characters SET image_path=? WHERE id=?', [request.form.get('image_path',''), id])
    db.commit(); db.close()
    return redirect(url_for('characters'))



# ─── Projects ─────────────────────────────────────────────────────────────────

@app.route('/projects')
def projects():
    db = get_db()
    items = db.execute(
        "SELECT p.*, COUNT(DISTINCT pj.job_id) as job_count, COUNT(DISTINCT pr.id) as prompt_count"
        " FROM projects p LEFT JOIN project_jobs pj ON pj.project_id=p.id"
        " LEFT JOIN prompts pr ON pr.project_id=p.id GROUP BY p.id ORDER BY p.created_at DESC"
    ).fetchall()
    db.close()
    return render_template('projects.html', items=items)

@app.route('/projects/add', methods=['POST'])
def add_project():
    db = get_db()
    db.execute('INSERT INTO projects (name, description, status) VALUES (?,?,?)',
               [request.form['name'], request.form.get('description',''), request.form.get('status','active')])
    db.commit(); db.close(); flash('Project created.')
    return redirect(url_for('projects'))

@app.route('/projects/edit/<int:id>', methods=['POST'])
def edit_project(id):
    db = get_db()
    db.execute('UPDATE projects SET name=?, description=?, status=?, notes=? WHERE id=?',
               [request.form['name'], request.form.get('description',''),
                request.form.get('status','active'), request.form.get('notes',''), id])
    db.commit(); db.close(); flash('Project updated.')
    return redirect(url_for('projects'))

@app.route('/projects/delete/<int:id>', methods=['POST'])
def delete_project(id):
    db = get_db()
    db.execute('DELETE FROM project_jobs WHERE project_id=?', [id])
    db.execute('DELETE FROM prompts WHERE project_id=?', [id])
    db.execute('DELETE FROM projects WHERE id=?', [id])
    db.commit(); db.close(); flash('Project deleted.')
    return redirect(url_for('projects'))

@app.route('/projects/<int:id>/link-job', methods=['POST'])
def link_project_job(id):
    db = get_db()
    job_id = request.form.get('job_id')
    if job_id:
        existing = db.execute('SELECT id FROM project_jobs WHERE project_id=? AND job_id=?',
                              [id, job_id]).fetchone()
        if not existing:
            db.execute('INSERT INTO project_jobs (project_id, job_id) VALUES (?,?)', [id, job_id])
            db.commit()
    db.close()
    return redirect(url_for('journal', project_id=id))

@app.route('/projects/<int:id>/unlink-job/<int:link_id>', methods=['POST'])
def unlink_project_job(id, link_id):
    db = get_db()
    db.execute('DELETE FROM project_jobs WHERE id=?', [link_id]); db.commit(); db.close()
    return redirect(url_for('journal', project_id=id))


# ─── Journal ──────────────────────────────────────────────────────────────────

@app.route('/journal')
def journal():
    db = get_db()
    project_id = request.args.get('project_id', type=int)
    projects_list = db.execute("SELECT * FROM projects WHERE status='active' ORDER BY name").fetchall()
    all_projects = db.execute('SELECT * FROM projects ORDER BY created_at DESC').fetchall()
    current_project = None
    linked_jobs = []
    prompts_list = []
    if project_id:
        current_project = db.execute('SELECT * FROM projects WHERE id=?', [project_id]).fetchone()
        linked_jobs = db.execute(
            "SELECT pj.id as link_id, rj.*, c.name as character_name, ot.name as output_type_name"
            " FROM project_jobs pj JOIN render_jobs rj ON pj.job_id=rj.id"
            " LEFT JOIN characters c ON rj.character_id=c.id"
            " LEFT JOIN output_types ot ON rj.output_type_id=ot.id"
            " WHERE pj.project_id=? ORDER BY rj.created_at DESC", [project_id]
        ).fetchall()
        prompts_list = db.execute(
            "SELECT * FROM prompts WHERE project_id=? ORDER BY created_at DESC", [project_id]
        ).fetchall()
    all_jobs = db.execute(
        "SELECT rj.*, c.name as character_name, ot.name as output_type_name FROM render_jobs rj"
        " LEFT JOIN characters c ON rj.character_id=c.id"
        " LEFT JOIN output_types ot ON rj.output_type_id=ot.id ORDER BY rj.created_at DESC"
    ).fetchall()
    db.close()
    return render_template('journal.html', projects=projects_list, all_projects=all_projects,
                           current_project=current_project, linked_jobs=linked_jobs,
                           prompts=prompts_list, all_jobs=all_jobs, project_id=project_id)


# ─── Prompts ──────────────────────────────────────────────────────────────────

@app.route('/prompts/add', methods=['POST'])
def add_prompt():
    db = get_db()
    db.execute('INSERT INTO prompts (project_id, job_id, text, label, status) VALUES (?,?,?,?,?)',
               [request.form.get('project_id') or None, request.form.get('job_id') or None,
                request.form.get('text',''), request.form.get('label',''), 'pending'])
    db.commit(); db.close()
    pid = request.form.get('project_id')
    return redirect(url_for('journal', project_id=pid) if pid else url_for('prompt_library'))

@app.route('/prompts/edit/<int:id>', methods=['POST'])
def edit_prompt(id):
    db = get_db()
    prompt = db.execute('SELECT * FROM prompts WHERE id=?', [id]).fetchone()
    db.execute('UPDATE prompts SET text=?, label=?, notes=? WHERE id=?',
               [request.form.get('text',''), request.form.get('label',''),
                request.form.get('notes',''), id])
    db.commit(); db.close()
    pid = prompt['project_id'] if prompt else None
    return redirect(url_for('journal', project_id=pid) if pid else url_for('prompt_library'))

@app.route('/prompts/delete/<int:id>', methods=['POST'])
def delete_prompt(id):
    db = get_db()
    prompt = db.execute('SELECT * FROM prompts WHERE id=?', [id]).fetchone()
    db.execute('DELETE FROM prompts WHERE id=?', [id]); db.commit(); db.close()
    pid = prompt['project_id'] if prompt else None
    return redirect(url_for('journal', project_id=pid) if pid else url_for('prompt_library'))

@app.route('/api/prompts/status/<int:id>', methods=['POST'])
def update_prompt_status(id):
    db = get_db()
    new_status = request.json.get('status')
    if new_status in ('pending', 'collected', 'done', 'flagged'):
        db.execute('UPDATE prompts SET status=? WHERE id=?', [new_status, id])
        db.commit()
    db.close()
    return jsonify({'ok': True})

@app.route('/prompt-library')
def prompt_library():
    db = get_db()
    project_filter = request.args.get('project_id','')
    status_filter = request.args.get('status','')
    query = ("SELECT p.*, proj.name as project_name, rj.id as job_num, c.name as character_name"
             " FROM prompts p LEFT JOIN projects proj ON p.project_id=proj.id"
             " LEFT JOIN render_jobs rj ON p.job_id=rj.id"
             " LEFT JOIN characters c ON rj.character_id=c.id WHERE 1=1")
    params = []
    if project_filter: query += ' AND p.project_id=?'; params.append(project_filter)
    if status_filter: query += ' AND p.status=?'; params.append(status_filter)
    query += ' ORDER BY p.created_at DESC'
    prompts_list = db.execute(query, params).fetchall()
    projects_list = db.execute('SELECT * FROM projects ORDER BY name').fetchall()
    db.close()
    return render_template('prompt_library.html', prompts=prompts_list, projects=projects_list,
                           project_filter=project_filter, status_filter=status_filter)


# ─── Dock ─────────────────────────────────────────────────────────────────────

@app.route('/dock')
def dock():
    db = get_db()
    config = db.execute('SELECT * FROM dock_config ORDER BY slot').fetchall()
    jobs = db.execute(
        "SELECT rj.*, c.name as character_name, ot.name as output_type_name FROM render_jobs rj"
        " LEFT JOIN characters c ON rj.character_id=c.id"
        " LEFT JOIN output_types ot ON rj.output_type_id=ot.id"
        " WHERE rj.status IN ('planned','in_progress','rendered')"
        " ORDER BY rj.created_at DESC LIMIT 20"
    ).fetchall()
    projects_list = db.execute("SELECT * FROM projects WHERE status='active' ORDER BY name").fetchall()
    db.close()
    return render_template('dock.html', config=config, jobs=jobs, projects=projects_list)

@app.route('/dock/config', methods=['POST'])
def save_dock_config():
    db = get_db()
    for slot in range(1, 6):
        label = request.form.get('label_' + str(slot), '')
        url_val = request.form.get('url_' + str(slot), '')
        db.execute('UPDATE dock_config SET label=?, url=? WHERE slot=?', [label, url_val, slot])
    db.commit(); db.close()
    flash('Dock configuration saved.')
    return redirect(url_for('dock'))

@app.route('/api/dock/job-prompts/<int:job_id>')
def api_dock_job_prompts(job_id):
    db = get_db()
    prompts = db.execute(
        "SELECT p.* FROM prompts p WHERE p.job_id=?"
        " OR p.project_id IN (SELECT project_id FROM project_jobs WHERE job_id=?)"
        " ORDER BY p.created_at DESC", [job_id, job_id]
    ).fetchall()
    db.close()
    return jsonify([dict(p) for p in prompts])

@app.route('/api/dock/submit-media', methods=['POST'])
def api_dock_submit_media():
    db = get_db()
    job_id = request.form.get('job_id')
    file_path = request.form.get('file_path', '')
    auto_title, auto_tags, char_id, ot_id = '', '', None, None
    if job_id:
        job = db.execute(
            "SELECT rj.*, c.name as character_name, c.tags as char_tags, ot.name as output_type_name"
            " FROM render_jobs rj LEFT JOIN characters c ON rj.character_id=c.id"
            " LEFT JOIN output_types ot ON rj.output_type_id=ot.id WHERE rj.id=?", [job_id]
        ).fetchone()
        if job:
            char_id = job['character_id']
            ot_id = job['output_type_id']
            auto_title = job['character_name'] or ''
            ings = db.execute(
                "SELECT i.name FROM render_job_ingredients rji"
                " JOIN ingredients i ON rji.ingredient_id=i.id WHERE rji.job_id=?", [job_id]
            ).fetchall()
            if ings:
                ing_names = ', '.join(i['name'] for i in ings)
                auto_title = (auto_title + ' — ' + ing_names) if auto_title else ing_names
            auto_tags = (job['character_name'] or '').lower().replace(' ', ',')
            if job['char_tags']: auto_tags += ',' + job['char_tags']
            if ings: auto_tags += ',' + ','.join(i['name'].lower() for i in ings)
            db.execute("UPDATE render_jobs SET status='complete' WHERE id=?", [job_id])
    new_id = db.execute(
        "INSERT INTO media_assets (job_id, character_id, output_type_id, file_path, title, tags, quality_status)"
        " VALUES (?,?,?,?,?,?,?)",
        [job_id or None, char_id, ot_id, file_path, auto_title, auto_tags, 'unreviewed']
    ).lastrowid
    db.commit(); db.close()
    return jsonify({'ok': True, 'media_id': new_id, 'title': auto_title})

@app.route('/api/dock/config')
def api_dock_config():
    db = get_db()
    config = db.execute('SELECT * FROM dock_config ORDER BY slot').fetchall()
    db.close()
    return jsonify([dict(c) for c in config])

@app.route('/api/dock/jobs')
def api_dock_jobs():
    db = get_db()
    project_id = request.args.get('project_id')
    query = ("SELECT rj.*, c.name as character_name, ot.name as output_type_name FROM render_jobs rj"
             " LEFT JOIN characters c ON rj.character_id=c.id"
             " LEFT JOIN output_types ot ON rj.output_type_id=ot.id"
             " WHERE rj.status IN ('planned','in_progress','rendered')")
    params = []
    if project_id:
        query += ' AND rj.id IN (SELECT job_id FROM project_jobs WHERE project_id=?)'
        params.append(project_id)
    query += ' ORDER BY rj.created_at DESC LIMIT 20'
    jobs = db.execute(query, params).fetchall()
    db.close()
    return jsonify([dict(j) for j in jobs])


if __name__ == '__main__':
    print("\n  Pipeline Manager is running.")
    print("  Open your browser and go to:  http://localhost:5000\n")
    app.run(debug=False, port=5000)
