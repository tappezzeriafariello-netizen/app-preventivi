"""
Sincronizzazione persistente con Google Drive (service account).

Variabili d'ambiente:
  GOOGLE_SERVICE_ACCOUNT_JSON  → contenuto JSON della chiave service account
  GOOGLE_DRIVE_FOLDER_ID       → ID cartella Drive condivisa con il service account
"""
from __future__ import annotations

import io
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]

_service = None
_folder_cache: dict[str, str] = {}


def enabled() -> bool:
    return bool(
        os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        and os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip()
    )


def _credentials():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON mancante")
    # Accetta JSON inline oppure percorso a file
    if raw.startswith("{"):
        info = json.loads(raw)
    else:
        info = json.loads(Path(raw).read_text(encoding="utf-8"))
    from google.oauth2 import service_account

    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


def get_service():
    global _service
    if _service is None:
        from googleapiclient.discovery import build

        _service = build("drive", "v3", credentials=_credentials(), cache_discovery=False)
    return _service


def root_folder_id() -> str:
    return os.environ["GOOGLE_DRIVE_FOLDER_ID"].strip()


def _find_child(parent_id: str, name: str, is_folder: bool) -> Optional[str]:
    svc = get_service()
    q = (
        f"'{parent_id}' in parents and name = '{name.replace(chr(39), chr(92)+chr(39))}' "
        f"and trashed = false"
    )
    if is_folder:
        q += " and mimeType = 'application/vnd.google-apps.folder'"
    else:
        q += " and mimeType != 'application/vnd.google-apps.folder'"
    res = (
        svc.files()
        .list(q=q, spaces="drive", fields="files(id, name)", pageSize=10)
        .execute()
    )
    files = res.get("files", [])
    return files[0]["id"] if files else None


def ensure_folder(path_parts: list[str]) -> str:
    """Crea (se serve) la catena di cartelle sotto la root e restituisce l'ID finale."""
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
            created = get_service().files().create(body=meta, fields="id").execute()
            parent = created["id"]
        _folder_cache[cache_key] = parent
    return parent


def _parent_and_name(rel_path: str) -> tuple[str, str]:
    rel = rel_path.replace("\\", "/").strip("/")
    parts = rel.split("/")
    name = parts[-1]
    if len(parts) == 1:
        return root_folder_id(), name
    parent = ensure_folder(parts[:-1])
    return parent, name


def upload_file(local_path: Path, rel_path: str) -> Optional[str]:
    if not enabled() or not local_path.exists() or not local_path.is_file():
        return None
    try:
        from googleapiclient.http import MediaFileUpload

        parent, name = _parent_and_name(rel_path)
        existing = _find_child(parent, name, is_folder=False)
        media = MediaFileUpload(str(local_path), resumable=True)
        svc = get_service()
        if existing:
            svc.files().update(fileId=existing, media_body=media).execute()
            logger.info("Drive update: %s", rel_path)
            return existing
        meta = {"name": name, "parents": [parent]}
        created = svc.files().create(body=meta, media_body=media, fields="id").execute()
        logger.info("Drive upload: %s", rel_path)
        return created["id"]
    except Exception:
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
        request = get_service().files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        local_path.write_bytes(buf.getvalue())
        logger.info("Drive download: %s", rel_path)
        return True
    except Exception:
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
        get_service().files().delete(fileId=file_id).execute()
        logger.info("Drive delete: %s", rel_path)
        return True
    except Exception:
        logger.exception("Delete Drive fallito: %s", rel_path)
        return False


def list_remote_files(rel_folder: str) -> list[str]:
    if not enabled():
        return []
    try:
        parts = [p for p in rel_folder.replace("\\", "/").strip("/").split("/") if p]
        parent = ensure_folder(parts) if parts else root_folder_id()
        res = (
            get_service()
            .files()
            .list(
                q=f"'{parent}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'",
                spaces="drive",
                fields="files(name)",
                pageSize=1000,
            )
            .execute()
        )
        return [f["name"] for f in res.get("files", [])]
    except Exception:
        logger.exception("List Drive fallito: %s", rel_folder)
        return []


def pull_data_tree(data_dir: Path) -> dict:
    """Scarica DB, logo e file da Drive verso la cache locale."""
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
                if download_file(f"files/{sub}/{name}", data_dir / "files" / sub / name):
                    stats["files"] += 1
        stats["ok"] = True
    except Exception:
        logger.exception("Pull Drive fallito")
    return stats


def push_db(db_path: Path) -> None:
    if not enabled() or not db_path.exists():
        return
    # Checkpoint WAL se presente, così il file .db è coerente
    try:
        con = sqlite3.connect(db_path)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.close()
    except Exception:
        pass
    upload_file(db_path, "preventivi.db")


def push_path(local_path: Path, rel_path: str) -> None:
    upload_file(local_path, rel_path)


def status() -> dict:
    if not enabled():
        return {"enabled": False, "message": "Drive non configurato"}
    try:
        email = json.loads(
            os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
            if os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"].strip().startswith("{")
            else Path(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]).read_text(encoding="utf-8")
        ).get("client_email", "")
        # ping: lista 1 file nella root
        get_service().files().list(
            q=f"'{root_folder_id()}' in parents and trashed = false",
            pageSize=1,
            fields="files(id)",
        ).execute()
        return {"enabled": True, "ok": True, "service_account": email}
    except Exception as exc:
        return {"enabled": True, "ok": False, "error": str(exc)}
