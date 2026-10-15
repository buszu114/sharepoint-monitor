"""Read-only SharePoint change monitor. Requires legitimate Graph access token."""
import asyncio
import base64
import json
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException

load_dotenv()
ROOT = Path(__file__).resolve().parent
DB = ROOT / 'monitor.db'
GRAPH = 'https://graph.microsoft.com/v1.0'


def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS files (id TEXT PRIMARY KEY, path TEXT, name TEXT, modified TEXT, size INTEGER, etag TEXT, ctag TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS changes (id INTEGER PRIMARY KEY AUTOINCREMENT, scanned_at TEXT, kind TEXT, path TEXT, name TEXT, details TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    db.commit()
    return db


def share_id(url):
    return 'u!' + base64.urlsafe_b64encode(url.encode()).decode().rstrip('=')


async def graph_get(client, url, token):
    response = await client.get(url, headers={'Authorization': f'Bearer {token}'})
    if response.status_code >= 400:
        raise RuntimeError(f'Graph HTTP {response.status_code}: {response.text[:350]}')
    return response.json()


async def collect_files():
    token = os.getenv('GRAPH_ACCESS_TOKEN', '').strip()
    url = os.getenv('SHARE_URL', '').strip()
    if not token or not url:
        raise RuntimeError('Brak GRAPH_ACCESS_TOKEN lub SHARE_URL. Wymagany autoryzowany dostęp Microsoft Graph.')
    if urlparse(url).scheme != 'https':
        raise RuntimeError('SHARE_URL musi być adresem HTTPS')
    result = {}
    async with httpx.AsyncClient(timeout=35, follow_redirects=False) as client:
        root = await graph_get(client, f'{GRAPH}/shares/{share_id(url)}/driveItem', token)
        drive_id = root.get('parentReference', {}).get('driveId')
        if not drive_id or 'folder' not in root:
            raise RuntimeError('Link nie udostępnia folderu lub Graph nie zwrócił identyfikatora dysku')
        pending = [(root['id'], '')]
        while pending:
            folder_id, prefix = pending.pop()
            next_url = f'{GRAPH}/drives/{drive_id}/items/{folder_id}/children?$top=200'
            while next_url:
                page = await graph_get(client, next_url, token)
                for item in page.get('value', []):
                    path = f'{prefix}/{item["name"]}'.lstrip('/')
                    if 'folder' in item:
                        pending.append((item['id'], path))
                    elif 'file' in item:
                        result[item['id']] = {'id': item['id'], 'path': path, 'name': item['name'],
                            'modified': item.get('lastModifiedDateTime', ''), 'size': item.get('size', 0),
                            'etag': item.get('eTag', ''), 'ctag': item.get('cTag', '')}
                next_url = page.get('@odata.nextLink')
                if next_url and not next_url.startswith(GRAPH + '/'):
                    raise RuntimeError('Nieprawidłowy link stronicowania Graph')
    return result


async def scan():
    # Fetch fully before touching the DB: a failed fetch cannot create false deletions.
    current = await collect_files()
    now = datetime.now(timezone.utc).isoformat()
    db = connect()
    try:
        previous = {r['id']: dict(r) for r in db.execute('SELECT * FROM files')}
        initialized = db.execute("SELECT value FROM settings WHERE key='initialized'").fetchone()
        changes = []
        if initialized:
            for key, item in current.items():
                old = previous.get(key)
                if old is None:
                    kind = 'nowy'
                elif old['path'] != item['path']:
                    kind = 'przeniesiony_lub_zmieniona_nazwa'
                elif any(str(old[k] or '') != str(item[k] or '') for k in ('modified', 'size', 'etag', 'ctag')):
                    kind = 'zmieniony'
                else:
                    continue
                changes.append((now, kind, item['path'], item['name'], json.dumps({'before': old, 'after': item}, ensure_ascii=False)))
            for key, old in previous.items():
                if key not in current:
                    changes.append((now, 'usuniety', old['path'], old['name'], '{}'))
        with db:
            db.execute('DELETE FROM files')
            db.executemany('INSERT INTO files VALUES (:id,:path,:name,:modified,:size,:etag,:ctag)', current.values())
            db.executemany('INSERT INTO changes (scanned_at,kind,path,name,details) VALUES (?,?,?,?,?)', changes)
            db.execute("INSERT OR REPLACE INTO settings VALUES ('initialized','1')")
            db.execute("INSERT OR REPLACE INTO settings VALUES ('last_scan',?)", (now,))
            db.execute("INSERT OR REPLACE INTO settings VALUES ('last_error','')")
        return {'scanned_at': now, 'files': len(current), 'changes': len(changes), 'first_scan': not bool(initialized)}
    finally:
        db.close()


async def poll():
    while True:
        try:
            await scan()
        except Exception as exc:
            db = connect()
            with db:
                db.execute("INSERT OR REPLACE INTO settings VALUES ('last_error',?)", (str(exc),))
            db.close()
        await asyncio.sleep(max(60, int(os.getenv('POLL_SECONDS', '900'))))


@asynccontextmanager
async def lifespan(app):
    db = connect(); db.close()
    task = asyncio.create_task(poll())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title='Monitor SharePoint', lifespan=lifespan)


def authorized(x_api_key):
    secret = os.getenv('API_KEY', '')
    if not secret or secret == 'replace-with-long-random-secret' or x_api_key != secret:
        raise HTTPException(status_code=401, detail='Brak prawidłowego klucza API')


@app.get('/status')
def status(x_api_key: str | None = Header(None)):
    authorized(x_api_key)
    db = connect()
    settings = {r['key']: r['value'] for r in db.execute('SELECT * FROM settings')}
    count = db.execute('SELECT COUNT(*) FROM files').fetchone()[0]
    db.close()
    return {'file_count': count, **settings}


@app.get('/changes')
def changes(x_api_key: str | None = Header(None), limit: int = 100):
    authorized(x_api_key)
    db = connect()
    rows = [dict(r) for r in db.execute('SELECT id,scanned_at,kind,path,name FROM changes ORDER BY id DESC LIMIT ?', (min(max(limit, 1), 500),))]
    db.close()
    return rows


@app.post('/scan')
async def run_scan(x_api_key: str | None = Header(None)):
    authorized(x_api_key)
    try:
        return await scan()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
