#!/usr/bin/env python3
"""Upload curated SARGuardian files to Google Drive with resumable streaming.

Never uploads the original raw product. Idempotent by exact filename+parent:
identical size+MD5 reuses the remote file; conflicting content fails closed.
"""
from __future__ import annotations
import argparse, hashlib, json, mimetypes, os, sys, time
from pathlib import Path
from urllib.parse import urlparse
import requests

API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
TOKEN = "https://oauth2.googleapis.com/token"
FOLDER_MIME = "application/vnd.google-apps.folder"
CHUNK_BYTES = 8 * 1024 * 1024  # 8 MiB; multiple of 256 KiB.

class DriveError(RuntimeError): pass

def hashes(path: Path) -> tuple[str, str, int]:
    md5, sha, size = hashlib.md5(), hashlib.sha256(), 0
    with path.open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            md5.update(block); sha.update(block); size += len(block)
    return md5.hexdigest(), sha.hexdigest(), size

def required_env(name: str) -> str:
    value = os.environ.get(name, '').strip()
    if not value: raise DriveError(f"MISSING_ENV_{name}")
    return value

class Drive:
    def __init__(self):
        try:
            raw = json.loads(required_env('GOOGLE_DRIVE_OAUTH_CLIENT_JSON'))
            client = raw.get('installed') or raw.get('web') or raw
            raw_refresh = required_env('GOOGLE_DRIVE_REFRESH_TOKEN')
            try:
                parsed = json.loads(raw_refresh)
                refresh = parsed.get('refresh_token') if isinstance(parsed, dict) else parsed
            except json.JSONDecodeError:
                refresh = raw_refresh
            self.client_id, self.client_secret, self.refresh = client['client_id'], client['client_secret'], refresh
            if not all(isinstance(v, str) and v for v in (self.client_id, self.client_secret, self.refresh)):
                raise ValueError()
        except Exception:
            raise DriveError('DRIVE_CONFIGURATION_INVALID') from None
        self.s = requests.Session()
        self.token = None
        self._refresh()

    def _refresh(self):
        try:
            r = self.s.post(TOKEN, data={'client_id': self.client_id, 'client_secret': self.client_secret,
                'refresh_token': self.refresh, 'grant_type': 'refresh_token'}, timeout=(15, 45))
            if r.status_code != 200: raise DriveError(f'DRIVE_TOKEN_REFRESH_HTTP_{r.status_code}')
            self.token = r.json().get('access_token')
            if not self.token: raise DriveError('DRIVE_TOKEN_REFRESH_INVALID')
        except requests.RequestException:
            raise DriveError('DRIVE_TOKEN_REFRESH_NETWORK_ERROR') from None

    def request(self, method, url, **kw):
        headers = kw.pop('headers', {})
        headers['Authorization'] = f'Bearer {self.token}'
        try: r = self.s.request(method, url, headers=headers, timeout=kw.pop('timeout', (20, 120)), **kw)
        except requests.RequestException: raise DriveError('DRIVE_API_NETWORK_ERROR') from None
        if r.status_code == 401:
            self._refresh(); headers['Authorization'] = f'Bearer {self.token}'
            try: r = self.s.request(method, url, headers=headers, timeout=(20, 120), **kw)
            except requests.RequestException: raise DriveError('DRIVE_API_NETWORK_ERROR') from None
        if r.status_code >= 400:
            raise DriveError(f'DRIVE_API_HTTP_{r.status_code}')
        return r

    @staticmethod
    def _q(s: str) -> str: return s.replace('\\', '\\\\').replace("'", "\\'")

    def list_named_children(self, parent, name):
        q = f"'{self._q(parent)}' in parents and name = '{self._q(name)}' and trashed = false"
        data = self.request('GET', f'{API}/files', params={'q': q, 'spaces': 'drive', 'pageSize': 100,
            'fields': 'files(id,name,mimeType,size,md5Checksum,parents,webViewLink)'}).json()
        return data.get('files', [])

    def ensure_folder(self, parent, name):
        rows = self.list_named_children(parent, name)
        folders = [x for x in rows if x.get('mimeType') == FOLDER_MIME]
        if any(x.get('mimeType') != FOLDER_MIME for x in rows): raise DriveError('DRIVE_FOLDER_NAME_CONFLICT')
        if len(folders) > 1: raise DriveError('DRIVE_DUPLICATE_FOLDER_CONFLICT')
        if folders: return folders[0]['id']
        data = {'name': name, 'mimeType': FOLDER_MIME, 'parents': [parent]}
        out = self.request('POST', f'{API}/files', params={'fields': 'id,name,mimeType,parents'}, json=data).json()
        if not out.get('id') or out.get('mimeType') != FOLDER_MIME: raise DriveError('DRIVE_FOLDER_CREATE_INVALID')
        return out['id']

    def quota(self):
        doc = self.request('GET', f'{API}/about', params={'fields': 'storageQuota(limit,usage,usageInDrive)'}).json()
        q = doc.get('storageQuota')
        if not isinstance(q, dict) or not q.get('limit') or q.get('usage') is None:
            raise DriveError('DRIVE_QUOTA_UNKNOWN_FAIL_CLOSED')
        return int(q['limit']), int(q['usage'])

    def upload_resumable(self, parent, path: Path, mime, md5, sha, size):
        existing = self.list_named_children(parent, path.name)
        files = [x for x in existing if x.get('mimeType') != FOLDER_MIME]
        if len(files) > 1: raise DriveError('DRIVE_DUPLICATE_FILE_CONFLICT')
        if files:
            item = files[0]
            try: remote_size = int(item.get('size', -1))
            except (TypeError, ValueError): remote_size = -1
            if remote_size == size and item.get('md5Checksum', '').lower() == md5.lower():
                return {'id': item['id'], 'name': path.name, 'bytes': size, 'md5': md5, 'sha256': sha, 'reused': True,
                        'webViewLink': item.get('webViewLink')}
            raise DriveError(f'DRIVE_EXISTING_FILE_CONFLICT name={path.name}')
        meta = {'name': path.name, 'parents': [parent], 'description': f'SARGuardian curated archive; sha256={sha}'}
        headers = {'X-Upload-Content-Type': mime, 'X-Upload-Content-Length': str(size), 'Content-Type': 'application/json; charset=UTF-8'}
        r = self.request('POST', UPLOAD, params={'uploadType': 'resumable', 'supportsAllDrives': 'true', 'fields': 'id,name,size,md5Checksum,parents,webViewLink'}, json=meta, headers=headers)
        session_url = r.headers.get('Location')
        parsed_session = urlparse(session_url or '')
        if parsed_session.scheme != 'https' or parsed_session.hostname not in {'www.googleapis.com', 'upload.googleapis.com'}:
            raise DriveError('DRIVE_RESUMABLE_SESSION_INVALID')
        offset = 0
        with path.open('rb') as f:
            while offset < size:
                f.seek(offset); block = f.read(min(CHUNK_BYTES, size - offset))
                if not block: raise DriveError('LOCAL_FILE_READ_SHORT')
                end = offset + len(block) - 1
                headers = {'Content-Type': mime, 'Content-Length': str(len(block)), 'Content-Range': f'bytes {offset}-{end}/{size}'}
                try: part = self.s.put(session_url, data=block, headers=headers, timeout=(20, 240))
                except requests.RequestException: raise DriveError('DRIVE_CHUNK_UPLOAD_NETWORK_ERROR') from None
                if part.status_code in (200, 201):
                    info = part.json(); break
                if part.status_code == 308:
                    rng = part.headers.get('Range', '')
                    if rng.startswith('bytes=0-'):
                        try: next_offset = int(rng.split('-', 1)[1]) + 1
                        except ValueError: raise DriveError('DRIVE_RESUMABLE_RANGE_INVALID') from None
                    else: raise DriveError('DRIVE_RESUMABLE_OFFSET_UNKNOWN')
                    if next_offset <= offset or next_offset > end + 1 or next_offset > size: raise DriveError('DRIVE_RESUMABLE_NO_PROGRESS')
                    offset = next_offset
                elif part.status_code >= 500:
                    raise DriveError(f'DRIVE_CHUNK_UPLOAD_HTTP_{part.status_code}')
                else: raise DriveError(f'DRIVE_CHUNK_UPLOAD_HTTP_{part.status_code}')
            else: raise DriveError('DRIVE_UPLOAD_FINISHED_WITHOUT_METADATA')
        try: remote_size = int(info.get('size', -1))
        except (TypeError, ValueError): remote_size = -1
        if not info.get('id') or remote_size != size or info.get('md5Checksum', '').lower() != md5.lower():
            raise DriveError('DRIVE_REMOTE_SIZE_OR_MD5_MISMATCH')
        return {'id': info['id'], 'name': path.name, 'bytes': size, 'md5': md5, 'sha256': sha, 'reused': False,
                'webViewLink': info.get('webViewLink')}

def granule_folder_names(product_type, maturity, granule_name, version_tag=None):
    """Return a deterministic folder path; optional version tags preserve prior runs."""
    if product_type not in {"GUNW", "GOFF"} or maturity not in {"PROVISIONAL", "BETA"}:
        raise DriveError("GRANULE_UPLOAD_REQUIRES_PRODUCT_MATURITY_AND_NAME")
    supplied = str(granule_name or "").strip()
    granule_folder = Path(supplied).name
    if granule_folder.lower().endswith(".h5"):
        granule_folder = granule_folder[:-3]
    if supplied != Path(supplied).name or "\\" in supplied:
        raise DriveError("GRANULE_NAME_INVALID")
    if not granule_folder.startswith("NISAR_L2_"):
        raise DriveError("GRANULE_NAME_INVALID")
    names = ["SARGuardian-DataArchive", product_type, maturity, granule_folder]
    if version_tag:
        if not __import__("re").fullmatch(r"[A-Za-z0-9_.-]{1,100}", version_tag):
            raise DriveError("VERSION_TAG_INVALID")
        names.extend(["Runs", version_tag])
    return names


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True, type=Path, help='folder containing curated archive/sidecars; raw product is excluded')
    p.add_argument('--product-type', choices=['GUNW', 'GOFF'])
    p.add_argument('--maturity', choices=['PROVISIONAL', 'BETA'])
    p.add_argument('--granule-name')
    p.add_argument('--run-name', help='upload an aggregate run bundle under SARGuardian-DataArchive/Runs/<run-name>')
    p.add_argument('--version-tag', help='isolate a granule upload under <granule>/Runs/<version-tag>; never overwrites prior runs')
    p.add_argument('--files', nargs='+', required=True, help='explicit local files to upload; raw source must NOT be included')
    p.add_argument('--out', required=True, type=Path)
    args = p.parse_args()
    if args.run_name:
        if args.version_tag:
            raise DriveError('RUN_UPLOAD_CANNOT_MIX_RUN_NAME_AND_VERSION_TAG')
        if args.product_type or args.maturity or args.granule_name:
            raise DriveError('RUN_UPLOAD_CANNOT_MIX_GRANULE_AND_RUN_IDENTIFIERS')
        if not __import__('re').fullmatch(r'[A-Za-z0-9_.-]{1,100}', args.run_name):
            raise DriveError('RUN_NAME_INVALID')
    elif not (args.product_type and args.maturity and args.granule_name):
        raise DriveError('GRANULE_UPLOAD_REQUIRES_PRODUCT_MATURITY_AND_NAME')
    root = args.root.resolve()
    files = [Path(x).resolve() for x in args.files]
    for path in files:
        if not path.is_file() or path == root: print('ERROR=UPLOAD_FILE_NOT_FOUND', file=sys.stderr); return 2
        if path.suffix.lower() in {'.h5', '.hdf5'} and not (path.name.endswith('.science.h5') or path.name.endswith('.curated.h5')):
            print('ERROR=REFUSING_TO_UPLOAD_RAW_HDF5', file=sys.stderr); return 2
        try: path.relative_to(root)
        except ValueError: print('ERROR=UPLOAD_FILE_OUTSIDE_ROOT', file=sys.stderr); return 2
    # The raw file may be in root itself. Explicit upload allowlist above only lets curated naming patterns pass.
    if len({x.name for x in files}) != len(files): print('ERROR=DUPLICATE_UPLOAD_BASENAMES', file=sys.stderr); return 2
    records = []
    local_total = 0
    for path in files:
        md5, sha, size = hashes(path); local_total += size
        mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        records.append((path, md5, sha, size, mime))
    drive = Drive()
    limit, usage = drive.quota()
    parent = required_env('GOOGLE_DRIVE_PARENT_FOLDER_ID')
    if args.run_name:
        folder_names = ['SARGuardian-DataArchive', 'Runs', args.run_name]
        granule_folder = None
    else:
        folder_names = granule_folder_names(
            args.product_type, args.maturity, args.granule_name, args.version_tag
        )
        granule_folder = Path(args.granule_name.strip()).name
        if granule_folder.lower().endswith('.h5'): granule_folder = granule_folder[:-3]
    folder = parent
    for name in folder_names: folder = drive.ensure_folder(folder, name)
    # Query exact existing names before calculating projected new bytes. Conflicts abort without overwrite.
    missing = 0
    for path, md5, sha, size, mime in records:
        existing = drive.list_named_children(folder, path.name)
        ordinary = [e for e in existing if e.get('mimeType') != FOLDER_MIME]
        if len(ordinary) > 1: raise DriveError('DRIVE_DUPLICATE_FILE_CONFLICT')
        if ordinary:
            e = ordinary[0]
            try: esize = int(e.get('size', -1))
            except (TypeError, ValueError): esize = -1
            if esize != size or e.get('md5Checksum', '').lower() != md5.lower(): raise DriveError(f'DRIVE_EXISTING_FILE_CONFLICT name={path.name}')
        else: missing += size
    # Quota is based on the exact post-processing files in this upload allowlist,
    # not source-file estimates from the acquisition manifest. This check runs
    # after the retained archive and derived outputs have actually been created.
    print(f"CURATED_UPLOAD_FILE_COUNT={len(records)}")
    print(f"CURATED_UPLOAD_ACTUAL_BYTES={local_total}")
    print(f"DRIVE_NEW_BYTES_REQUIRED_ACTUAL={missing}")
    if usage + missing > limit:
        raise DriveError(
            "DRIVE_QUOTA_INSUFFICIENT "
            f"curated_files={len(records)} actual_curated_bytes={local_total} "
            f"required_new_bytes={missing} remaining_bytes={max(0, limit-usage)}"
        )
    print(
        "DRIVE_ACTUAL_OUTPUT_QUOTA_CHECK=PASS "
        f"FILE_COUNT={len(records)} ACTUAL_CURATED_BYTES={local_total} "
        f"NEW_BYTES_REQUIRED={missing}"
    )
    outputs = []
    for path, md5, sha, size, mime in records:
        row = drive.upload_resumable(folder, path, mime, md5, sha, size)
        outputs.append(row)
        print(f"DRIVE_FILE_VERIFIED name={path.name} bytes={size} reused={str(row['reused']).lower()}")
    receipt = {'schema_version':'sarguardian-drive-retention-receipt/1.0','created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'upload_kind':'run_bundle' if args.run_name else 'single_granule',
        'run_name':args.run_name, 'product_type':args.product_type, 'maturity':args.maturity, 'version_tag':args.version_tag,
        'granule_name':granule_folder, 'remote_folder_id':folder,'files':outputs,
        'uploaded_curated_bytes':sum(x['bytes'] for x in outputs),
        'raw_product_uploaded':False,'remote_verification':'PASS','raw_source_deleted':False}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(f"DRIVE_VERIFICATION=PASS FILE_COUNT={len(outputs)} REMOTE_FOLDER_ID={folder} RECEIPT={args.out}")
    return 0

if __name__ == '__main__':
    try: raise SystemExit(main())
    except DriveError as e:
        print(f'ERROR={e}', file=sys.stderr); raise SystemExit(2)
