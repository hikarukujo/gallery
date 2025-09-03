# Smart Gallery for ComfyUI 
# Author: Biagio Maffettone
# Contact: biagiomaf@gmail.com

import os
import hashlib
import cv2
import json
import shutil
import re
import sqlite3
import time
import glob
from flask import Flask, render_template, send_from_directory, abort, send_file, url_for, redirect, request, jsonify, Response
from PIL import Image, ImageSequence

# --- USER CONFIGURATION ---
# Modify the parameters in this section to adapt the gallery to your needs.

# Path to the ComfyUI 'output' folder.
BASE_OUTPUT_PATH = 'C:/sm/Data/Packages/ComfyUI/output'
# Path to the ComfyUI 'input' folder (for searching .json workflows)
BASE_INPUT_PATH = 'C:/sm/Data/Packages/ComfyUI/input'


# Port on which the gallery web server will run.
SERVER_PORT = 8189

# Width in pixels of the generated thumbnails.
THUMBNAIL_WIDTH = 300

# Assumed framerate for animated WebP files.
# Many tools, including ComfyUI, generate WebP at about 16 FPS.
# Change this value if your WebPs have a different framerate,
# for an accurate calculation of their animation duration.
WEBP_ANIMATED_FPS = 16.0

# Maximum number of files to load initially (use a high number for "infinite").
PAGE_SIZE = 999999

# Names of special folders (e.g., 'video', 'audio').
# These folders will be shown in the menu only if they already exist inside BASE_OUTPUT_PATH.
SPECIAL_FOLDERS = ['video', 'audio']

# Names for cache folders, the database file, and workflows
THUMBNAIL_CACHE_FOLDER_NAME = '.thumbnails_cache'
SQLITE_CACHE_FOLDER_NAME = '.sqlite_cache'
DATABASE_FILENAME = 'gallery_cache.sqlite'
WORKFLOW_FOLDER_NAME = 'workflow_logs_success'

# --- END OF USER CONFIGURATION ---


# --- DERIVED SETTINGS (Do not modify) ---
BASE_INPUT_PATH_WORKFLOW = os.path.join(BASE_INPUT_PATH, WORKFLOW_FOLDER_NAME)
THUMBNAIL_CACHE_DIR = os.path.join(BASE_OUTPUT_PATH, THUMBNAIL_CACHE_FOLDER_NAME)
SQLITE_CACHE_DIR = os.path.join(BASE_OUTPUT_PATH, SQLITE_CACHE_FOLDER_NAME)
DATABASE_FILE = os.path.join(SQLITE_CACHE_DIR, DATABASE_FILENAME)
PROTECTED_FOLDER_KEYS = {'_root_'}.union(SPECIAL_FOLDERS)

app = Flask(__name__)
gallery_view_cache = []

def initialize_gallery():
    """Creates cache directories, moves the old DB if necessary, and synchronizes."""
    print("Initializing gallery...")

    os.makedirs(THUMBNAIL_CACHE_DIR, exist_ok=True)
    os.makedirs(SQLITE_CACHE_DIR, exist_ok=True)

    init_db()
    sync_database()
    print("Initialization complete.")

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Creates the 'files' table in the database if it doesn't exist."""
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, mtime REAL NOT NULL,
                name TEXT NOT NULL, type TEXT, duration TEXT, dimensions TEXT,
                has_workflow INTEGER, is_favorite INTEGER DEFAULT 0
            )
        ''')
        conn.commit()

def get_dynamic_folder_config():
    """Dynamically builds the list of folders to display."""
    dynamic_config = {'_root_': {'display_name': 'Main', 'path': BASE_OUTPUT_PATH}}

    for folder_name in SPECIAL_FOLDERS:
        folder_path = os.path.join(BASE_OUTPUT_PATH, folder_name)
        if os.path.isdir(folder_path):
            dynamic_config[folder_name] = {'display_name': folder_name.title(), 'path': folder_path}

    try:
        for item in os.listdir(BASE_OUTPUT_PATH):
            full_path = os.path.join(BASE_OUTPUT_PATH, item)
            if os.path.isdir(full_path) and not item.startswith('.') and item not in dynamic_config:
                dynamic_config[item] = {'display_name': item.replace('_', ' ').replace('-', ' ').title(), 'path': full_path}
    except FileNotFoundError:
        print(f"WARNING: The base directory '{BASE_OUTPUT_PATH}' was not found.")

    return dynamic_config

def sync_database():
    """Synchronizes the state of files on disk with the database."""
    print("Starting database synchronization...")
    start_time = time.time()
    with get_db_connection() as conn:
        db_files = {row['path']: row['mtime'] for row in conn.execute('SELECT path, mtime FROM files').fetchall()}
        disk_files = {}
        all_folder_paths = [config['path'] for config in get_dynamic_folder_config().values()]

        for folder_path in all_folder_paths:
            if not os.path.isdir(folder_path): continue
            for name in os.listdir(folder_path):
                filepath = os.path.join(folder_path, name)
                if os.path.isfile(filepath) and os.path.splitext(name)[1].lower() not in ['.json', '.sqlite']:
                    disk_files[filepath] = os.path.getmtime(filepath)

        to_add = set(disk_files) - set(db_files)
        to_delete = set(db_files) - set(disk_files)
        to_check = set(disk_files) & set(db_files)
        to_update = {path for path in to_check if disk_files[path] > db_files.get(path, 0)}

        if to_add:
            new_files_data = [(hashlib.md5(p.encode()).hexdigest(), p, disk_files[p], os.path.basename(p), *analyze_file_metadata(p).values()) for p in to_add]
            conn.executemany("INSERT OR REPLACE INTO files (id, path, mtime, name, type, duration, dimensions, has_workflow) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", new_files_data)
        if to_delete: conn.executemany("DELETE FROM files WHERE path = ?", [(p,) for p in to_delete])
        if to_update:
            updated_files_data = [(disk_files[p], *analyze_file_metadata(p).values(), p) for p in to_update]
            conn.executemany("UPDATE files SET mtime=?, type=?, duration=?, dimensions=?, has_workflow=? WHERE path=?", updated_files_data)
        conn.commit()
    print(f"Synchronization completed in {time.time() - start_time:.2f} seconds.")

def analyze_file_metadata(filepath):
    """Extracts metadata from a file (type, dimensions, duration, etc.)."""
    details = {'type': 'unknown', 'duration': '', 'dimensions': '', 'has_workflow': 0}
    ext_lower = os.path.splitext(filepath)[1].lower()

    type_map = {'.png': 'image', '.jpg': 'image', '.jpeg': 'image', '.gif': 'animated_image',
                '.mp4': 'video', '.webm': 'video', '.mov': 'video', '.mp3': 'audio', '.wav': 'audio', '.ogg': 'audio'}
    details['type'] = type_map.get(ext_lower, 'unknown')
    if details['type'] == 'unknown' and ext_lower == '.webp':
        details['type'] = 'animated_image' if is_webp_animated(filepath) else 'image'

    if 'image' in details['type']:
        try:
            with Image.open(filepath) as img:
                details['dimensions'] = f"{img.width}x{img.height}"
        except Exception as e:
            print(f"Pillow error for {filepath}: {e}")

    # Regardless of the file type, search for an associated workflow
    if extract_workflow(filepath):
        details['has_workflow'] = 1

    total_duration_sec = 0
    if details['type'] == 'video':
        try:
            cap = cv2.VideoCapture(filepath)
            if cap.isOpened():
                fps, count = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
                if fps > 0 and count > 0: total_duration_sec = count / fps
                cap.release()
        except Exception: pass
    elif details['type'] == 'animated_image':
        try:
            with Image.open(filepath) as img:
                if getattr(img, 'is_animated', False):
                    if ext_lower == '.gif':
                        total_duration_sec = sum(frame.info.get('duration', 100) for frame in ImageSequence.Iterator(img)) / 1000
                    elif ext_lower == '.webp':
                        total_duration_sec = getattr(img, 'n_frames', 1) / WEBP_ANIMATED_FPS
        except Exception as e: print(f"Animation error for {filepath}: {e}")

    if total_duration_sec > 0: details['duration'] = format_duration(total_duration_sec)
    return details

# The rest of the code (utilities and Flask routes) remains unchanged...

def sanitize_folder_name(name):
    if not name or not isinstance(name, str): return None
    return re.sub(r'[^a-zA-Z0-9_-]', '', name).strip()

def format_duration(seconds):
    if not seconds or seconds < 0: return ""
    m, s = divmod(int(seconds), 60); h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

def is_webp_animated(filepath):
    try:
        with Image.open(filepath) as img: return getattr(img, 'is_animated', False)
    except: return False

def extract_workflow(filepath):
    """
    Extracts the workflow from a file.
    First, it checks the image metadata (for PNGs),
    then it looks for a corresponding .json file in the input folder.
    """
    # 1. Try to extract from the image metadata
    try:
        with Image.open(filepath) as img:
            # This part mainly works for PNG files generated by ComfyUI
            workflow_data = img.info.get('workflow') or img.info.get('prompt')
            if workflow_data and isinstance(workflow_data, str) and workflow_data.strip().startswith('{'):
                json.loads(workflow_data)
                return workflow_data
    except Exception:
        # Ignore errors if the file is not an image or has no metadata
        pass

    # 2. If not found, search for a corresponding .json file in the input folder
    try:
        base_filename = os.path.basename(filepath)
        # Builds a search pattern for JSON files
        search_pattern = os.path.join(BASE_INPUT_PATH_WORKFLOW, f"{base_filename}*.json")

        # Finds all JSON files that match the pattern
        json_files = glob.glob(search_pattern)

        if json_files:
            # If it finds multiple files, use the most recent one
            latest_json_file = max(json_files, key=os.path.getmtime)

            with open(latest_json_file, 'r', encoding='utf-8') as f:
                workflow_json = f.read()
                # Validate that it is a valid JSON
                json.loads(workflow_json)
                return workflow_json
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        # Ignore errors if the JSON file does not exist, is corrupt, or is not the most recent
        print(f"No valid JSON workflow found for {base_filename}: {e}")
        pass

    return None

@app.route('/galleryout/')
@app.route('/')
def gallery_redirect_base():
    return redirect(url_for('gallery_view', folder_key='_root_'))

@app.route('/galleryout/view/<string:folder_key>')
def gallery_view(folder_key):
    sync_database()
    global gallery_view_cache
    folders = get_dynamic_folder_config()
    if folder_key not in folders:
        return redirect(url_for('gallery_view', folder_key='_root_'))

    with get_db_connection() as conn:
        folder_path = folders[folder_key]['path']
        conditions, params = [], []

        search_term = request.args.get('search', '').strip()
        if search_term:
            conditions.append("name LIKE ?")
            params.append(f"%{search_term}%")

        selected_extensions = request.args.getlist('extension')
        if selected_extensions:
            conditions.append(f"({ ' OR '.join(['name LIKE ?']*len(selected_extensions)) })")
            params.extend([f"%.{ext.lstrip('.')}" for ext in selected_extensions])

        selected_prefixes = request.args.getlist('prefix')
        if selected_prefixes:
            conditions.append(f"({ ' OR '.join(['name LIKE ?']*len(selected_prefixes)) })")
            params.extend([f"{pfx}%" for pfx in selected_prefixes])

        if request.args.get('favorites', 'false').lower() == 'true':
            conditions.append("is_favorite = 1")

        query = f"SELECT * FROM files {'WHERE ' + ' AND '.join(conditions) if conditions else ''} ORDER BY mtime DESC"
        all_files_raw = conn.execute(query, params).fetchall()

    folder_path_norm = os.path.normpath(folder_path)
    all_files_filtered = [dict(row) for row in all_files_raw if os.path.normpath(os.path.dirname(row['path'])) == folder_path_norm]

    gallery_view_cache = all_files_filtered
    initial_files = gallery_view_cache[:PAGE_SIZE]

    _, extensions, prefixes = scan_folder_and_extract_options(folder_path)

    return render_template('index.html', files=initial_files, total_files=len(gallery_view_cache), folders=folders,
                           current_folder_key=folder_key, current_folder_name=folders[folder_key]['display_name'],
                           available_extensions=extensions, available_prefixes=prefixes,
                           selected_extensions=selected_extensions, selected_prefixes=selected_prefixes,
                           show_favorites=request.args.get('favorites', 'false').lower() == 'true', protected_folder_keys=PROTECTED_FOLDER_KEYS)

def scan_folder_and_extract_options(folder_path):
    extensions, prefixes = set(), set()
    try:
        for filename in os.listdir(folder_path):
            if os.path.isfile(os.path.join(folder_path, filename)):
                ext = os.path.splitext(filename)[1]
                if ext and ext.lower() not in ['.json', '.sqlite']:
                    extensions.add(ext.lstrip('.').lower())
                if '_' in filename:
                    prefixes.add(filename.split('_')[0])
    except FileNotFoundError: pass
    return None, sorted(list(extensions)), sorted(list(prefixes))

@app.route('/galleryout/create_folder', methods=['POST'])
def create_folder():
    folder_name = sanitize_folder_name(request.json.get('folder_name'))
    if not folder_name: return jsonify({'status': 'error', 'message': 'Invalid folder name.'}), 400
    if folder_name in get_dynamic_folder_config(): return jsonify({'status': 'error', 'message': 'Folder name already in use or protected.'}), 400

    new_folder_path = os.path.join(BASE_OUTPUT_PATH, folder_name)
    try:
        os.makedirs(new_folder_path); return jsonify({'status': 'success', 'message': 'Folder created.'})
    except Exception as e: return jsonify({'status': 'error', 'message': f'Error: {e}'}), 500

@app.route('/galleryout/rename_folder/<string:folder_key>', methods=['POST'])
def rename_folder(folder_key):
    if folder_key in PROTECTED_FOLDER_KEYS: return jsonify({'status': 'error', 'message': 'Cannot rename a protected folder.'}), 403

    new_name = sanitize_folder_name(request.json.get('new_name'))
    if not new_name or new_name in get_dynamic_folder_config(): return jsonify({'status': 'error', 'message': 'New name is invalid or already in use.'}), 400

    folders = get_dynamic_folder_config()
    if folder_key not in folders: return jsonify({'status': 'error', 'message': 'Folder not found.'}), 404

    old_path, new_path = folders[folder_key]['path'], os.path.join(BASE_OUTPUT_PATH, new_name)
    try:
        os.rename(old_path, new_path); sync_database(); return jsonify({'status': 'success', 'message': 'Folder renamed.'})
    except Exception as e: return jsonify({'status': 'error', 'message': f'Error: {e}'}), 500

@app.route('/galleryout/delete_folder/<string:folder_key>', methods=['POST'])
def delete_folder(folder_key):
    if folder_key in PROTECTED_FOLDER_KEYS: return jsonify({'status': 'error', 'message': 'Cannot delete a protected folder.'}), 403

    folders = get_dynamic_folder_config()
    if folder_key not in folders: return jsonify({'status': 'error', 'message': 'Folder not found.'}), 404

    try:
        shutil.rmtree(folders[folder_key]['path']); return jsonify({'status': 'success', 'message': 'Folder deleted.'})
    except OSError as e:
        if "not empty" in str(e).lower():
            return jsonify({'status': 'error', 'message': 'The folder is not empty.'}), 400
        return jsonify({'status': 'error', 'message': f'Error: {e}'}), 500
    except Exception as e: return jsonify({'status': 'error', 'message': f'Error: {e}'}), 500

@app.route('/galleryout/load_more')
def load_more():
    offset = request.args.get('offset', 0, type=int)
    if offset >= len(gallery_view_cache): return jsonify(files=[])
    return jsonify(files=gallery_view_cache[offset:offset + PAGE_SIZE])

def get_file_info_from_db(file_id, column='*'):
    with get_db_connection() as conn:
        row = conn.execute(f"SELECT {column} FROM files WHERE id = ?", (file_id,)).fetchone()
    if not row: abort(404)
    return dict(row) if column == '*' else row[0]

@app.route('/galleryout/move_batch', methods=['POST'])
def move_batch():
    data = request.json
    file_ids, dest_key = data.get('file_ids', []), data.get('destination_folder')
    folders = get_dynamic_folder_config()
    
    if not all([file_ids, dest_key, dest_key in folders]):
        return jsonify({'status': 'error', 'message': 'Invalid data provided.'}), 400

    # We will track files that failed to move to provide specific feedback to the user.
    failed_moves = []
    moved_count = 0
    
    # Get destination folder details for creating paths and user messages.
    dest_folder_info = folders[dest_key]
    dest_path_folder = dest_folder_info['path']
    dest_folder_display_name = dest_folder_info['display_name']

    with get_db_connection() as conn:
        for file_id in file_ids:
            try:
                # Get the current path of the file from the database.
                source_path = conn.execute("SELECT path FROM files WHERE id = ?", (file_id,)).fetchone()['path']
                source_filename = os.path.basename(source_path)
                
                # Construct the full destination path for the file.
                dest_path_file = os.path.join(dest_path_folder, source_filename)

                # --- CONTROL POINT ---
                # This is the new check. Verify if a file with the same name already exists at the destination.
                if os.path.exists(dest_path_file):
                    # If the file exists, add its details to the 'failed_moves' list for the final report.
                    failed_moves.append({
                        'filename': source_filename,
                        'destination_folder': dest_folder_display_name
                    })
                    # Skip the rest of the loop for this file and proceed to the next one.
                    continue
                
                # If the destination is clear, move the file.
                shutil.move(source_path, dest_path_file)
                
                # After moving, update the database with the new path and a new ID based on that path.
                new_id = hashlib.md5(dest_path_file.encode()).hexdigest()
                conn.execute("UPDATE files SET id = ?, path = ? WHERE id = ?", (new_id, dest_path_file, file_id))
                
                moved_count += 1

            except (TypeError, KeyError):
                # This handles cases where a file_id from the request is not found in the database.
                print(f"Warning: Could not find file with id {file_id} in the database. Skipping.")
                continue

        conn.commit()

    # After processing all files, build the response based on the outcome.
    if failed_moves:
        # If there are any failed moves, create a detailed list of error messages.
        error_messages = [f"File '{item['filename']}' cannot be moved because it already exists in folder '{item['destination_folder']}'" for item in failed_moves]
        
        # Create a summary message for the user.
        if moved_count > 0:
            message = f"Moved {moved_count} file(s), but {len(failed_moves)} file(s) failed."
        else:
            message = "No files were moved because they already exist in the destination."

        # Return a response containing the summary and the list of specific errors.
        # The frontend can use the 'errors' list to display a detailed alert.
        return jsonify({
            'status': 'partial_success' if moved_count > 0 else 'error',
            'message': message,
            'errors': error_messages
        })
    
    # If all files were moved successfully, return a simple success message.
    return jsonify({
        'status': 'success',
        'message': f'Successfully moved {moved_count} file(s).'
    })
    
    
@app.route('/galleryout/delete_batch', methods=['POST'])
def delete_batch():
    file_ids = request.json.get('file_ids', [])
    if not file_ids: return jsonify({'status': 'error', 'message': 'No files selected'}), 400

    with get_db_connection() as conn:
        placeholders = ','.join('?' * len(file_ids))
        files_to_delete = conn.execute(f"SELECT path FROM files WHERE id IN ({placeholders})", file_ids).fetchall()
        for row in files_to_delete:
            try: os.remove(row['path'])
            except OSError as e: print(f"Error deleting file {row['path']}: {e}")

        conn.execute(f"DELETE FROM files WHERE id IN ({placeholders})", file_ids)
        conn.commit()
    return jsonify({'status': 'success', 'message': f'Deleted {len(file_ids)} files.'})

@app.route('/galleryout/favorite_batch', methods=['POST'])
def favorite_batch():
    data = request.json
    file_ids, status = data.get('file_ids', []), data.get('status', False)
    if not file_ids: return jsonify({'status': 'error', 'message': 'No files selected'}), 400

    with get_db_connection() as conn:
        placeholders = ','.join('?' * len(file_ids))
        conn.execute(f"UPDATE files SET is_favorite = ? WHERE id IN ({placeholders})", [1 if status else 0] + file_ids)
        conn.commit()
    return jsonify({'status': 'success'})

@app.route('/galleryout/toggle_favorite/<string:file_id>', methods=['POST'])
def toggle_favorite(file_id):
    with get_db_connection() as conn:
        current = conn.execute("SELECT is_favorite FROM files WHERE id = ?", (file_id,)).fetchone()
        if not current: abort(404)
        new_status = 1 - current['is_favorite']
        conn.execute("UPDATE files SET is_favorite = ? WHERE id = ?", (new_status, file_id))
        conn.commit()
        return jsonify({'status': 'success', 'is_favorite': bool(new_status)})

@app.route('/galleryout/file/<string:file_id>')
def serve_file(file_id):
    filepath = get_file_info_from_db(file_id, 'path')

    # Check if the file is a WebP to set the correct Content-Type
    if filepath.lower().endswith('.webp'):
        # Send the file specifying that it is a WebP image
        # and disabling conditional responses to force a reload
        return send_file(filepath, mimetype='image/webp', conditional=False)

    # For all other files, let Flask behave as usual
    return send_file(filepath)

@app.route('/galleryout/download/<string:file_id>')
def download_file(file_id):
    filepath = get_file_info_from_db(file_id, 'path')
    return send_from_directory(os.path.dirname(filepath), os.path.basename(filepath), as_attachment=True)

@app.route('/galleryout/workflow/<string:file_id>')
def download_workflow(file_id):
    filepath = get_file_info_from_db(file_id, 'path')
    workflow_json = extract_workflow(filepath) # Use the new unified function
    if workflow_json:
        return Response(workflow_json, mimetype='application/json', headers={'Content-Disposition': 'attachment;filename=workflow.json'})
    abort(404)

@app.route('/galleryout/delete/<string:file_id>', methods=['POST'])
def delete_file(file_id):
    filepath = get_file_info_from_db(file_id, 'path')
    os.remove(filepath)
    with get_db_connection() as conn:
        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
        conn.commit()
    return jsonify({'status': 'success'})

@app.route('/galleryout/thumbnail/<string:file_id>')
def serve_thumbnail(file_id):
    info = get_file_info_from_db(file_id)
    filepath, mtime = info['path'], info['mtime']
    file_hash = hashlib.md5((filepath + str(mtime)).encode()).hexdigest()

    try:
        with Image.open(filepath) as img:
            fmt = 'jpeg' if img.format == 'JPEG' else img.format.lower()
            cache_path = os.path.join(THUMBNAIL_CACHE_DIR, f"{file_hash}.{fmt}")

            if os.path.exists(cache_path): return send_file(cache_path)

            if info['type'] == 'animated_image' and getattr(img, 'is_animated', False):
                frames = [fr.copy() for fr in ImageSequence.Iterator(img)]
                if frames:
                    for i in range(len(frames)):
                        frames[i].thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 2), Image.Resampling.LANCZOS)
                    frames[0].save(cache_path, save_all=True, append_images=frames[1:], duration=img.info.get('duration', 100), loop=img.info.get('loop', 0), optimize=True)
            else:
                img.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 2), Image.Resampling.LANCZOS)
                if img.mode != 'RGB': img = img.convert('RGB')
                img.save(cache_path, 'JPEG', quality=85)

            return send_file(cache_path)
    except Exception as e:
        print(f"Error generating thumbnail for {filepath}: {e}")
        # Send a generic placeholder if you don't have a static file
        return Response(status=404)

if __name__ == '__main__':
    initialize_gallery()
    print(f"Gallery started! Open: http://127.0.0.1:{SERVER_PORT}/galleryout/")
    app.run(host='0.0.0.0', port=SERVER_PORT, debug=True)