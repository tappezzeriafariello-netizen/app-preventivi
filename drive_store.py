"""
Sincronizzazione persistente con Google Drive.

Auth supportate (in ordine di priorità):
  1) OAuth utente (consigliato — funziona con Gmail personale):
       GOOGLE_OAUTH_CLIENT_ID
       GOOGLE_OAUTH_CLIENT_SECRET
       GOOGLE_OAUTH_REFRESH_TOKEN
       GOOGLE_DRIVE_FOLDER_ID

  2) Service account (spesso FALLISCE su Gmail: quota 0):
       GOOGLE_SERVICE_ACCOUNT_JSON
       GOOGLE_DRIVE_FOLDER_ID
"""
from __future__ import annotations

import io
import json
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]

_service = None
_folder_cache: dict[str, str] = {}
_lock = threading.Lock()
_last_error: Optional[str] = None


def _set_error(msg: Optional[str]) -> None:
    global _last_error
    _last_error = msg


def last_error() -> Optional[str]:
    return _last_error


def _oauth_configured() -> bool:
    return bool(
        os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
        and os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
        and os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN", "").strip()
        and os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
    )


def _sa_configured() -> bool:
    return bool(
        os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        and os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
    )


def enabled() -> bool:
    return _oauth_configured() or _sa_configured()


def auth_mode() -> str:
    if _oauth_configured():
        return "oauth"
    if _sa_configured():
        return "service_account"
    return "none"


def root_folder_id() -> str:
    return os.environ["GOOGLE_DRIVE_FOLDER_ID"].strip()


def _load_sa_info() -> dict:
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw.startswith("{"):
        return json.loads(raw)
    return json.loads(Path(raw).read_text(encoding="utf-8"))


def _credentials():
    if _oauth_configured():
        from google.oauth2.credentials import Credentials

        return Credentials(
            token=None,
            refresh_token=os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"].strip(),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["GOOGLE_OAUTH_CLIENT_ID"].strip(),
            client_secret=os.environ["GOOGLE_OAUTH_CLIENT_SECRET"].strip(),
            scopes=SCOPES,
        )
    if _sa_configured():
        from google.oauth2 import service_account

        return service_account.Credentials.from_service_account_info(
            _load_sa_info(), scopes=SCOPES
        )
    raise RuntimeError("Credenziali Google Drive non configurate")


def get_service():
    global _service
    with _lock:
        if _service is None:
            from googleapiclient.discovery import build

            _service = build(
                "drive", "v3", credentials=_credentials(), cache_discovery=False
            )
        return _service


def _api_kwargs() -> dict[str, Any]:
    return {
        "supportsAllDrives": True,
    }


def _escape_q(name: str) -> str:
    return name.replace("\\", "\\\\").replace("'", "\\'")


def _find_child(parent_id: str, name: str, is_folder: bool) -> Optional[str]:
    svc = get_service()
    q = (
        f"'{parent_id}' in parents and name = '{_escape_q(name)}' and trashed = false"
    )
    if is_folder:
        q += " and mimeType = 'application/vnd.google-apps.folder'"
    else:
        q += " and mimeType != 'application/vnd.google-apps.folder'"
    res = (
        svc.files()
        .list(
            q=q,
            spaces="drive",
            fields="files(id, name)",
            pageSize=10,
            includeItemsFromAllDrives=True,
            **_api_kwargs(),
        )
        .execute()
    )
    files = res.get("files", [])
    return files[0]["id"] if files else None


def ensure_folder(path_parts: list[str]) -> str:
    key = "/".join(path_parts)
    if key in _folder_cache:
        return _folder_cache[key]

    parent = root_folder_id()
    walked: list[str] = []
    for part in path_parts:
        walked.append(part)
        cache_key = "/".join(walked)
        if cache_key in _folder_cache:
            parent = _folder_cache[cache_key]
            continue
        existing = _find_child(parent, part, is_folder=True)
        if existing:
            parent = existing
        else:
            meta = {
                "name": part,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent],
            }
            created = (
                get_service()
                .files()
                .create(body=meta, fields="id", **_api_kwargs())
                .execute()
            )
            parent = created["id"]
        _folder_cache[cache_key] = parent
    return parent


def _parent_and_name(rel_path: str) -> tuple[str, str]:
    rel = rel_path.replace("\\", "/").strip("/")
    parts = rel.split("/")
    name = parts[-1]
    if len(parts) == 1:
        return root_folder_id(), name
    return ensure_folder(parts[:-1]), name


def upload_file(local_path: Path, rel_path: str) -> Optional[str]:
    if not enabled():
        return None
    if not local_path.exists() or not local_path.is_file():
        _set_error(f"File locale assente: {local_path}")
        return None
    try:
        from googleapiclient.http import MediaFileUpload

        parent, name = _parent_and_name(rel_path)
        existing = _find_child(parent, name, is_folder=False)
        media = MediaFileUpload(str(local_path), resumable=True)
        svc = get_service()
        if existing:
            svc.files().update(
                fileId=existing, media_body=media, **_api_kwargs()
            ).execute()
            logger.info("Drive update: %s", rel_path)
            _set_error(None)
            return existing
        meta = {"name": name, "parents": [parent]}
        created = (
            svc.files()
            .create(body=meta, media_body=media, fields="id", **_api_kwargs())
            .execute()
        )
        logger.info("Drive upload: %s", rel_path)
        _set_error(None)
        return created["id"]
    except Exception as exc:
        msg = str(exc)
        if "storageQuotaExceeded" in msg or "storage quota" in msg.lower():
            msg = (
                "Quota Drive insufficiente per l'account di servizio. "
                "Usa OAuth (script get_drive_token.py) al posto della service account."
            )
        _set_error(f"Upload fallito ({rel_path}): {msg}")
        logger.exception("Upload Drive fallito: %s", rel_path)
        return None


def download_file(rel_path: str, local_path: Path) -> bool:
    if not enabled():
        return False
    try:
        from googleapiclient.http import MediaIoBaseDownload

        parent, name = _parent_and_name(rel_path)
        file_id = _find_child(parent, name, is_folder=False)
        if not file_id:
            return False
        local_path.parent.mkdir(parents=True, exist_ok=True)
        request = get_service().files().get_media(fileId=file_id, **_api_kwargs())
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        local_path.write_bytes(buf.getvalue())
        logger.info("Drive download: %s", rel_path)
        return True
    except Exception as exc:
        _set_error(f"Download fallito ({rel_path}): {exc}")
        logger.exception("Download Drive fallito: %s", rel_path)
        return False


def delete_remote(rel_path: str) -> bool:
    if not enabled():
        return False
    try:
        parent, name = _parent_and_name(rel_path)
        file_id = _find_child(parent, name, is_folder=False)
        if not file_id:
            return False
        get_service().files().delete(fileId=file_id, **_api_kwargs()).execute()
        logger.info("Drive delete: %s", rel_path)
        return True
    except Exception as exc:
        _set_error(f"Delete fallito ({rel_path}): {exc}")
        logger.exception("Delete Drive fallito: %s", rel_path)
        return False


def list_remote_files_detailed(rel_folder: str) -> list[dict]:
    if not enabled():
        return []
    try:
        parts = [p for p in rel_folder.replace("\\", "/").strip("/").split("/") if p]
        parent = ensure_folder(parts) if parts else root_folder_id()
        res = (
            get_service()
            .files()
            .list(
                q=(
                    f"'{parent}' in parents and trashed = false "
                    f"and mimeType != 'application/vnd.google-apps.folder'"
                ),
                spaces="drive",
                fields="files(id, name, size, modifiedTime)",
                pageSize=1000,
                includeItemsFromAllDrives=True,
                **_api_kwargs(),
            )
            .execute()
        )
        out = []
        for f in res.get("files", []):
            out.append(
                {
                    "id": f["id"],
                    "name": f["name"],
                    "size": int(f.get("size") or 0),
                    "mtime": f.get("modifiedTime") or "",
                }
            )
        return out
    except Exception as exc:
        _set_error(f"List fallito ({rel_folder}): {exc}")
        logger.exception("List Drive fallito: %s", rel_folder)
        return []


def list_remote_files(rel_folder: str) -> list[str]:
    return [f["name"] for f in list_remote_files_detailed(rel_folder)]


def pull_data_tree(data_dir: Path) -> dict:
    stats = {"db": False, "files": 0, "ok": False}
    if not enabled():
        return stats
    try:
        stats["db"] = download_file("preventivi.db", data_dir / "preventivi.db")
        for name in list_remote_files("logo"):
            if download_file(f"logo/{name}", data_dir / "logo" / name):
                stats["files"] += 1
        for sub in ("preventivi", "pdf"):
            for name in list_remote_files(f"files/{sub}"):
                if download_file(
                    f"files/{sub}/{name}", data_dir / "files" / sub / name
                ):
                    stats["files"] += 1
        stats["ok"] = True
    except Exception as exc:
        _set_error(f"Pull fallito: {exc}")
        logger.exception("Pull Drive fallito")
    return stats


def push_db(db_path: Path) -> bool:
    if not enabled() or not db_path.exists():
        return False
    try:
        con = sqlite3.connect(db_path)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.close()
    except Exception:
        pass
    return upload_file(db_path, "preventivi.db") is not None


def push_path(local_path: Path, rel_path: str) -> bool:
    return upload_file(local_path, rel_path) is not None


def test_write() -> dict:
    """Prova reale di scrittura su Drive (non solo lettura)."""
    if not enabled():
        return {"ok": False, "error": "Drive non configurato"}
    try:
        from googleapiclient.http import MediaIoBaseUpload

        name = "_preventivi_write_test.txt"
        parent = root_folder_id()
        existing = _find_child(parent, name, is_folder=False)
        content = io.BytesIO(b"ok")
        media = MediaIoBaseUpload(content, mimetype="text/plain")
        svc = get_service()
        if existing:
            svc.files().update(
                fileId=existing, media_body=media, **_api_kwargs()
            ).execute()
            file_id = existing
        else:
            created = (
                svc.files()
                .create(
                    body={"name": name, "parents": [parent]},
                    media_body=media,
                    fields="id",
                    **_api_kwargs(),
                )
                .execute()
            )
            file_id = created["id"]
        _set_error(None)
        return {"ok": True, "file_id": file_id, "mode": auth_mode()}
    except Exception as exc:
        msg = str(exc)
        if "storageQuotaExceeded" in msg or "storage quota" in msg.lower():
            msg = (
                "L'account di servizio NON può salvare file su Drive (quota 0). "
                "Configura OAuth con get_drive_token.py e le variabili "
                "GOOGLE_OAUTH_CLIENT_ID / SECRET / REFRESH_TOKEN."
            )
        _set_error(msg)
        return {"ok": False, "error": msg, "mode": auth_mode()}


def status() -> dict:
    if not enabled():
        return {
            "enabled": False,
            "message": "Drive non configurato",
            "mode": "none",
        }
    mode = auth_mode()
    account = ""
    try:
        if mode == "service_account":
            account = _load_sa_info().get("client_email", "")
        # ping lettura
        get_service().files().list(
            q=f"'{root_folder_id()}' in parents and trashed = false",
            pageSize=1,
            fields="files(id)",
            includeItemsFromAllDrives=True,
            **_api_kwargs(),
        ).execute()
        write = test_write()
        if not write.get("ok"):
            return {
                "enabled": True,
                "ok": False,
                "mode": mode,
                "service_account": account,
                "error": write.get("error"),
                "can_read": True,
                "can_write": False,
            }
        return {
            "enabled": True,
            "ok": True,
            "mode": mode,
            "service_account": account,
            "can_read": True,
            "can_write": True,
        }
    except Exception as exc:
        return {
            "enabled": True,
            "ok": False,
            "mode": mode,
            "service_account": account,
            "error": str(exc),
            "can_read": False,
            "can_write": False,
        }
