"""Runway REST contract and crash-safe, conservative per-campaign reservations.

Live submission is disabled by default. No credentials or signed URLs are persisted.
"""
import hashlib
import json
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

API = 'https://api.dev.runwayml.com'
VERSION = '2024-11-06'
CAP_CENTS = 1000


class SecureRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme != 'https':
            raise ValueError('Refusing non-HTTPS redirect')
        if request.has_header('Authorization') and parsed.netloc != urlsplit(API).netloc:
            raise ValueError('Refusing authenticated redirect to another host')
        return super().redirect_request(request, fp, code, message, headers, newurl)


def open_https(request, timeout=60):
    return urllib.request.build_opener(SecureRedirect()).open(request, timeout=timeout)


class RunwayError(ValueError):
    pass


class RunwayClient:
    def __init__(self, token=None, *, allow_paid=False, opener=open_https, sleep=time.sleep):
        self.token, self.allow_paid, self.opener, self.sleep = token, allow_paid is True, opener, sleep

    def request(self, method, path, body=None):
        if not self.allow_paid or not self.token:
            raise RunwayError('Live API access is locked: user approval and verified prices are required')
        if method not in ('GET', 'POST') or not path.startswith('/v1/'):
            raise RunwayError('Unsupported API operation')
        headers = {'Authorization': 'Bearer ' + self.token, 'X-Runway-Version': VERSION,
                   'Content-Type': 'application/json'}
        request = urllib.request.Request(API + path, data=json.dumps(body).encode() if body else None,
                                         headers=headers, method=method)
        # A POST can be accepted even when the response is lost. Never auto-repeat it.
        for attempt in range(4 if method == 'GET' else 1):
            try:
                with self.opener(request, timeout=60) as response:
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                if method == 'GET' and exc.code in (429, 500, 502, 503, 504) and attempt < 3:
                    try:
                        delay = min(30, max(1, float(exc.headers.get('Retry-After', 2 ** attempt))))
                    except (TypeError, ValueError):
                        delay = 2 ** attempt
                    self.sleep(delay)
                    continue
                raise RunwayError(f'Runway HTTP {exc.code}; response body omitted; no generation resubmitted') from None
            except (urllib.error.URLError, TimeoutError):
                if method == 'GET' and attempt < 3:
                    self.sleep(2 ** attempt)
                    continue
                raise RunwayError('Runway transport failure; submission outcome may be unknown') from None
        raise RunwayError('Retry limit exceeded')

    def create(self, kind, payload):
        if kind not in ('video', 'audio'):
            raise RunwayError('Unsupported generation kind')
        endpoint = '/v1/text_to_video' if kind == 'video' else '/v1/sound_effect'
        return self.request('POST', endpoint, payload)['id']

    def wait(self, task_id):
        # Validate identifiers before embedding them in a URL.
        if not task_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in task_id):
            raise RunwayError('Invalid task ID')
        for _ in range(180):
            result = self.request('GET', '/v1/tasks/' + task_id)
            status = result.get('status')
            if status == 'SUCCEEDED':
                return result
            if status in ('FAILED', 'CANCELLED'):
                raise RunwayError('Generation task ' + status + '; no automatic paid regeneration')
            if status not in ('PENDING', 'THROTTLED', 'RUNNING'):
                raise RunwayError('Unknown task status')
            self.sleep(10)
        raise RunwayError('Task polling timed out; task ID retained for resume')


    def materialize(self, job, task_id, target):
        result = self.wait(task_id)
        outputs = result.get('output')
        if not isinstance(outputs, list) or len(outputs) != 1:
            raise RunwayError('Expected one output artifact')
        self.download(outputs[0], target)

    def download(self, url, target):
        if not self.allow_paid:
            raise RunwayError('Live output download is locked')
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise RunwayError('Output URL must use HTTPS without embedded credentials')
        target = Path(target)
        partial = target.with_suffix(target.suffix + '.partial')
        # Separate request: never forward the Runway Authorization header to the media host.
        for attempt in range(4):
            try:
                request = urllib.request.Request(url, headers={'Accept': 'application/octet-stream'})
                with self.opener(request, timeout=60) as source, partial.open('wb') as destination:
                    final_url = source.geturl() if hasattr(source, 'geturl') else url
                    if urlsplit(final_url).scheme != 'https':
                        raise RunwayError('Output redirect did not preserve HTTPS')
                    size = 0
                    while True:
                        block = source.read(1024 * 1024)
                        if not block:
                            break
                        size += len(block)
                        if size > 1_000_000_000:
                            raise RunwayError('Output artifact exceeds 1 GB')
                        destination.write(block)
                    if not size:
                        raise RunwayError('Empty output artifact')
                partial.replace(target)
                return
            except urllib.error.HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                    raise RunwayError(f'Output download HTTP {exc.code}; URL and body omitted') from None
            except (urllib.error.URLError, TimeoutError):
                if attempt == 3:
                    raise RunwayError('Output download retry limit reached; task retained') from None
            finally:
                if partial.exists():
                    partial.unlink()
            self.sleep(2 ** attempt)


def task_key(kind, payload):
    return hashlib.sha256(json.dumps([VERSION, kind, payload], sort_keys=True).encode()).hexdigest()


class Ledger:
    """Reservations include failures and unknown outcomes; never assume a refund."""
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS tasks (key TEXT PRIMARY KEY, cents INTEGER NOT NULL, state TEXT NOT NULL, task_id TEXT)')
        self.db.commit()

    def reserve(self, jobs):
        # One transaction reserves the entire plan before any network request.
        self.db.execute('BEGIN IMMEDIATE')
        try:
            for job in jobs:
                if type(job['cents']) is not int or job['cents'] <= 0:
                    raise RunwayError('Every task needs a verified positive integer cent ceiling')
                existing = self.db.execute('SELECT cents FROM tasks WHERE key=?', (job['key'],)).fetchone()
                if existing and existing[0] != job['cents']:
                    raise RunwayError('Price changed; existing campaign reservations cannot be reinterpreted')
                self.db.execute('INSERT OR IGNORE INTO tasks VALUES (?, ?, ?, NULL)',
                                (job['key'], job['cents'], 'reserved'))
            total = self.db.execute('SELECT COALESCE(SUM(cents),0) FROM tasks').fetchone()[0]
            if total > CAP_CENTS:
                raise RunwayError('Campaign exceeds the $10.00 ceiling; no task submitted')
            self.db.commit()
            return total
        except BaseException:
            self.db.rollback()
            raise

    def row(self, key):
        return self.db.execute('SELECT state, task_id FROM tasks WHERE key=?', (key,)).fetchone()

    def update(self, key, state, task_id=None):
        self.db.execute('UPDATE tasks SET state=?, task_id=COALESCE(?,task_id) WHERE key=?', (state, task_id, key))
        self.db.commit()

    def submit(self, job, client):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.row(job['key'])
            if row is None:
                raise RunwayError('Task must be reserved before submission')
            state, task_id = row
            if task_id:
                self.db.commit()
                return task_id
            if state != 'reserved':
                raise RunwayError('Submission outcome unknown; reconcile with Runway before resuming, never resubmit')
            # Atomic claim committed before POST, including across separate connections.
            self.db.execute('UPDATE tasks SET state=? WHERE key=?', ('submitting', job['key']))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        task_id = client.create(job['kind'], job['payload'])
        if not isinstance(task_id, str) or not task_id:
            raise RunwayError('Missing task ID; submission remains ambiguous')
        self.update(job['key'], 'submitted', task_id)
        return task_id

    def close(self):
        self.db.close()
