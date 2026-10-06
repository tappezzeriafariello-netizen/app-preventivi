"""
Gestione Preventivi - Web App (Flask + SQLite)
Gratuita, utilizzabile dal browser su qualsiasi dispositivo.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime
from functools import wraps
from io import BytesIO
from pathlib import Path

from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

import drive_store

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
FILES_DIR = DATA_DIR / "files"
DB_PATH = DATA_DIR / "preventivi.db"
LOGO_DIR = DATA_DIR / "logo"

ALLOWED_LOGO = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_UPLOAD = {".prev", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".json"}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "preventivi-dev-cambia-in-produzione")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

# Password opzionale: se APP_PASSWORD non è impostata, niente login.
APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    (FILES_DIR / "preventivi").mkdir(exist_ok=True)
    (FILES_DIR / "pdf").mkdir(exist_ok=True)
    LOGO_DIR.mkdir(parents=True, exist_ok=True)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    ensure_dirs()
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS azienda (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            titolo TEXT DEFAULT '',
            bio TEXT DEFAULT '',
            piva TEXT DEFAULT '',
            cf TEXT DEFAULT '',
            iban TEXT DEFAULT '',
            logo_path TEXT DEFAULT ''
        );
        INSERT OR IGNORE INTO azienda (id) VALUES (1);

        CREATE TABLE IF NOT EXISTS clienti (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS preventivi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT NOT NULL,
            data TEXT NOT NULL,
            consegna TEXT DEFAULT '',
            pagamento TEXT DEFAULT '',
            iva REAL DEFAULT 0,
            sconto REAL DEFAULT 0,
            acconto REAL DEFAULT 0,
            articoli_json TEXT NOT NULL,
            totale REAL DEFAULT 0,
            saldo REAL DEFAULT 0,
            nome_file TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS auth (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            password_hash TEXT
        );
        """
    )
    db.commit()
    if APP_PASSWORD:
        row = db.execute("SELECT password_hash FROM auth WHERE id = 1").fetchone()
        if not row:
            db.execute(
                "INSERT INTO auth (id, password_hash) VALUES (1, ?)",
                (generate_password_hash(APP_PASSWORD),),
            )
            db.commit()
    db.close()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if APP_PASSWORD and not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text or "preventivo"


def pulisci_testo(testo: str) -> str:
    if not testo:
        return ""
    sostituzioni = {
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
        "\u00a0": " ",
        "€": "EUR",
    }
    for originale, pulito in sostituzioni.items():
        testo = testo.replace(originale, pulito)
    return testo


def calcola_totali(articoli: list, iva_perc: float, sconto_perc: float, acconto_perc: float):
    imponibile = sum(float(a.get("totale", 0)) for a in articoli)
    valore_iva = imponibile * (iva_perc / 100)
    totale = imponibile + valore_iva
    valore_sconto = totale * (sconto_perc / 100)
    totale_scontato = totale - valore_sconto
    valore_acconto = totale_scontato * (acconto_perc / 100)
    saldo = totale_scontato - valore_acconto
    return {
        "imponibile": imponibile,
        "valore_iva": valore_iva,
        "totale": totale,
        "valore_sconto": valore_sconto,
        "totale_scontato": totale_scontato,
        "valore_acconto": valore_acconto,
        "saldo": saldo,
    }


def get_azienda() -> dict:
    row = get_db().execute("SELECT * FROM azienda WHERE id = 1").fetchone()
    return dict(row) if row else {}


def genera_pdf_bytes(dati: dict, azienda: dict) -> bytes:
    articoli = dati["articoli"]
    iva = float(dati.get("iva") or 0)
    sconto = float(dati.get("sconto") or 0)
    acconto = float(dati.get("acconto") or 0)
    t = calcola_totali(articoli, iva, sconto, acconto)
    cliente = dati.get("cliente", "")

    pdf = FPDF()
    pdf.add_page()

    logo = azienda.get("logo_path") or ""
    logo_full = BASE_DIR / logo if logo and not os.path.isabs(logo) else Path(logo) if logo else None
    if logo_full and logo_full.exists():
        try:
            pdf.image(str(logo_full), x=10, y=8, w=40)
        except Exception:
            pass

    pdf.set_font("Helvetica", style="B", size=14)
    pdf.cell(
        0,
        6,
        text=pulisci_testo((azienda.get("titolo") or "").upper()),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
        align="R",
    )
    pdf.set_font("Helvetica", size=9)
    pdf.multi_cell(0, 5, text=pulisci_testo(azienda.get("bio") or ""), align="R")
    pdf.cell(
        0,
        5,
        text=pulisci_testo(
            f"P.IVA: {azienda.get('piva', '')} | C.F.: {azienda.get('cf', '')}"
        ),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
        align="R",
    )
    pdf.ln(15)

    pdf.set_font("Helvetica", style="B", size=16)
    pdf.cell(100, 8, text="PREVENTIVO", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf.set_font("Helvetica", style="B", size=10)
    pdf.cell(
        90,
        8,
        text=pulisci_testo(f"SPETT. {cliente.upper()}"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
        align="R",
    )
    pdf.set_font("Helvetica", size=10)
    pdf.cell(
        0,
        6,
        text=pulisci_testo(f"DATA: {dati.get('data', '')}"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.cell(
        0,
        6,
        text=pulisci_testo(f"DATA CONSEGNA: {dati.get('consegna', '')}"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.cell(
        0,
        6,
        text=pulisci_testo(f"PAGAMENTO: {dati.get('pagamento', '')}"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(8)

    pdf.set_font("Helvetica", style="B", size=9)
    pdf.cell(15, 8, text="Q.TA'", border=1, align="C")
    pdf.cell(115, 8, text="DESCRIZIONE OGGETTO", border=1, align="L")
    pdf.cell(30, 8, text="PREZZO UNIT.", border=1, align="C")
    pdf.cell(30, 8, text="PREZZO TOT.", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

    pdf.set_font("Helvetica", size=9)
    for art in articoli:
        pdf.cell(15, 8, text=str(art["qty"]), border=1, align="C")
        desc = art["desc"] if len(art["desc"]) < 65 else art["desc"][:62] + "..."
        pdf.cell(115, 8, text=pulisci_testo(desc), border=1, align="L")
        pdf.cell(30, 8, text=f"EUR {float(art['prezzo']):.2f}", border=1, align="R")
        pdf.cell(
            30,
            8,
            text=f"EUR {float(art['totale']):.2f}",
            border=1,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
            align="R",
        )
    pdf.ln(10)

    pdf.set_font("Helvetica", size=10)
    pdf.cell(150, 6, text="IMPONIBILE:", align="R")
    pdf.cell(40, 6, text=f"EUR {t['imponibile']:.2f}", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    if t["valore_iva"] > 0:
        pdf.cell(150, 6, text=f"IVA ({iva:g}%):", align="R")
        pdf.cell(40, 6, text=f"EUR {t['valore_iva']:.2f}", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", style="B", size=10)
        pdf.cell(150, 6, text="TOTALE:", align="R")
        pdf.cell(40, 6, text=f"EUR {t['totale']:.2f}", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", size=10)

    if t["valore_sconto"] > 0:
        pdf.cell(150, 6, text=f"SCONTO ({sconto:g}%):", align="R")
        pdf.cell(40, 6, text=f"- EUR {t['valore_sconto']:.2f}", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    if t["valore_acconto"] > 0:
        pdf.cell(150, 6, text=f"ACCONTO ({acconto:g}%):", align="R")
        pdf.cell(40, 6, text=f"- EUR {t['valore_acconto']:.2f}", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", style="B", size=12)
    pdf.cell(150, 8, text="SALDO:", align="R")
    pdf.cell(40, 8, text=f"EUR {t['saldo']:.2f}", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(15)

    pdf.set_font("Helvetica", style="B", size=9)
    pdf.multi_cell(
        0,
        5,
        text=pulisci_testo(
            "N.B. IL SALDO DEVE ESSERE EFFETTUATO TASSATIVAMENTE PRIMA DELLA CONSEGNA DELLA MERCE"
        ),
        align="C",
    )
    pdf.ln(5)
    pdf.set_font("Helvetica", size=9)
    pdf.cell(
        0,
        5,
        text=pulisci_testo(f"Dati per Bonifico: {azienda.get('iban', '')}"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
        align="C",
    )
    pdf.ln(20)
    pdf.cell(95, 5, text="Il produttore", align="C")
    pdf.cell(95, 5, text="Il committente", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.cell(95, 10, text="_______________________", align="C")
    pdf.cell(95, 10, text="_______________________", align="C")

    out = BytesIO()
    pdf.output(out)
    return out.getvalue()


def upsert_cliente(nome: str) -> None:
    nome = (nome or "").strip()
    if not nome:
        return
    get_db().execute("INSERT OR IGNORE INTO clienti (nome) VALUES (?)", (nome,))
    get_db().commit()


def sync_db() -> bool:
    """Chiude eventuali connessioni e carica il DB su Drive."""
    db = g.pop("db", None)
    if db is not None:
        db.close()
    return drive_store.push_db(DB_PATH)


def sync_file(local: Path, rel: str) -> bool:
    return drive_store.push_path(local, rel)


def sync_delete(rel: str) -> bool:
    return drive_store.delete_remote(rel)


def safe_rel_path(folder: str, name: str) -> Path | None:
    """Evita path traversal: restituisce path assoluto sotto FILES_DIR o None."""
    folder = (folder or "").replace("\\", "/").strip("/")
    name = secure_filename(name)
    if not name:
        return None
    base = FILES_DIR / folder if folder else FILES_DIR
    try:
        base = base.resolve()
        target = (base / name).resolve()
        if not str(target).startswith(str(FILES_DIR.resolve())):
            return None
        return target
    except Exception:
        return None


# ---------- Auth ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if not APP_PASSWORD:
        return redirect(url_for("index"))
    if request.method == "POST":
        pwd = request.form.get("password", "")
        row = get_db().execute("SELECT password_hash FROM auth WHERE id = 1").fetchone()
        ok = False
        if row and row["password_hash"]:
            ok = check_password_hash(row["password_hash"], pwd)
        else:
            ok = pwd == APP_PASSWORD
        if ok:
            session["logged_in"] = True
            return redirect(request.args.get("next") or url_for("index"))
        flash("Password non corretta.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login" if APP_PASSWORD else "index"))


# ---------- Pagine ----------
@app.route("/")
@login_required
def index():
    clienti = [
        r["nome"]
        for r in get_db().execute("SELECT nome FROM clienti ORDER BY nome").fetchall()
    ]
    azienda = get_azienda()
    preventivo_id = request.args.get("id", type=int)
    preventivo = None
    if preventivo_id:
        row = get_db().execute(
            "SELECT * FROM preventivi WHERE id = ?", (preventivo_id,)
        ).fetchone()
        if row:
            preventivo = dict(row)
            preventivo["articoli"] = json.loads(preventivo["articoli_json"])
    return render_template(
        "index.html",
        clienti=clienti,
        azienda=azienda,
        preventivo=preventivo,
        today=datetime.now().strftime("%d/%m/%Y"),
    )


@app.route("/azienda")
@login_required
def azienda_page():
    return render_template(
        "azienda.html",
        azienda=get_azienda(),
        drive=drive_store.status(),
    )


@app.route("/archivio")
@login_required
def archivio():
    rows = get_db().execute(
        "SELECT id, cliente, data, totale, saldo, nome_file, updated_at FROM preventivi ORDER BY updated_at DESC"
    ).fetchall()
    return render_template("archivio.html", preventivi=rows)


@app.route("/files")
@login_required
def files_page():
    folder = request.args.get("folder", "preventivi")
    if folder not in ("preventivi", "pdf", ""):
        folder = "preventivi"
    path = FILES_DIR / folder if folder else FILES_DIR
    path.mkdir(parents=True, exist_ok=True)

    # Allinea la cache locale con Drive (così i file non "spariscono" a caso)
    if drive_store.enabled():
        for remote in drive_store.list_remote_files_detailed(f"files/{folder}"):
            local = path / remote["name"]
            if not local.exists():
                drive_store.download_file(f"files/{folder}/{remote['name']}", local)

    items = []
    for p in sorted(path.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.name.startswith("."):
            continue
        items.append(
            {
                "name": p.name,
                "size": p.stat().st_size,
                "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
                "is_dir": p.is_dir(),
                "folder": folder,
            }
        )
    return render_template(
        "files.html",
        items=items,
        folder=folder,
        drive_error=drive_store.last_error(),
        drive_enabled=drive_store.enabled(),
    )


# ---------- API Azienda / Clienti ----------
@app.route("/api/azienda", methods=["GET", "POST"])
@login_required
def api_azienda():
    db = get_db()
    if request.method == "GET":
        return jsonify(get_azienda())

    titolo = request.form.get("titolo", "").strip()
    bio = request.form.get("bio", "").strip()
    piva = request.form.get("piva", "").strip()
    cf = request.form.get("cf", "").strip()
    iban = request.form.get("iban", "").strip()

    azienda = get_azienda()
    logo_path = azienda.get("logo_path") or ""

    if "logo" in request.files:
        f = request.files["logo"]
        if f and f.filename:
            ext = Path(f.filename).suffix.lower()
            if ext in ALLOWED_LOGO:
                name = f"logo{ext}"
                dest = LOGO_DIR / name
                f.save(dest)
                logo_path = str(dest.relative_to(BASE_DIR)).replace("\\", "/")
                sync_file(dest, f"logo/{name}")

    db.execute(
        """UPDATE azienda SET titolo=?, bio=?, piva=?, cf=?, iban=?, logo_path=? WHERE id=1""",
        (titolo, bio, piva, cf, iban, logo_path),
    )
    db.commit()
    sync_db()
    msg = "Impostazioni azienda salvate."
    if drive_store.enabled():
        msg += " Sincronizzate su Google Drive."
    flash(msg, "ok")
    return redirect(url_for("azienda_page"))


@app.route("/api/clienti", methods=["GET", "POST", "DELETE"])
@login_required
def api_clienti():
    db = get_db()
    if request.method == "GET":
        rows = db.execute("SELECT id, nome FROM clienti ORDER BY nome").fetchall()
        return jsonify([dict(r) for r in rows])

    data = request.get_json(silent=True) or {}
    if request.method == "POST":
        nome = (data.get("nome") or "").strip()
        if not nome:
            return jsonify({"error": "Nome mancante"}), 400
        upsert_cliente(nome)
        sync_db()
        return jsonify({"ok": True})

    nome = (data.get("nome") or "").strip()
    if nome:
        db.execute("DELETE FROM clienti WHERE nome = ?", (nome,))
        db.commit()
        sync_db()
    return jsonify({"ok": True})


# ---------- API Preventivi ----------
@app.route("/api/preventivi", methods=["POST"])
@login_required
def api_salva_preventivo():
    data = request.get_json(force=True)
    articoli = data.get("articoli") or []
    if not articoli:
        return jsonify({"error": "Nessun articolo"}), 400

    cliente = (data.get("cliente") or "").strip()
    upsert_cliente(cliente)

    iva = float(str(data.get("iva", 0)).replace(",", ".") or 0)
    sconto = float(str(data.get("sconto", 0)).replace(",", ".") or 0)
    acconto = float(str(data.get("acconto", 0)).replace(",", ".") or 0)
    for a in articoli:
        a["qty"] = int(a["qty"])
        a["prezzo"] = float(str(a["prezzo"]).replace(",", "."))
        a["totale"] = a["qty"] * a["prezzo"]
        a["desc"] = str(a.get("desc", "")).strip()

    tot = calcola_totali(articoli, iva, sconto, acconto)
    now = datetime.now().isoformat(timespec="seconds")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{stamp}_{slugify(cliente or 'senza-cliente')}"

    payload = {
        "cliente": cliente,
        "data": data.get("data") or datetime.now().strftime("%d/%m/%Y"),
        "consegna": data.get("consegna") or "",
        "pagamento": data.get("pagamento") or "",
        "iva": iva,
        "sconto": sconto,
        "acconto": acconto,
        "articoli": articoli,
    }

    prev_path = FILES_DIR / "preventivi" / f"{base_name}.prev"
    prev_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    pdf_bytes = genera_pdf_bytes(payload, get_azienda())
    pdf_path = FILES_DIR / "pdf" / f"{base_name}.pdf"
    pdf_path.write_bytes(pdf_bytes)

    db = get_db()
    pid = data.get("id")
    if pid:
        db.execute(
            """UPDATE preventivi SET cliente=?, data=?, consegna=?, pagamento=?,
               iva=?, sconto=?, acconto=?, articoli_json=?, totale=?, saldo=?,
               nome_file=?, updated_at=? WHERE id=?""",
            (
                cliente,
                payload["data"],
                payload["consegna"],
                payload["pagamento"],
                iva,
                sconto,
                acconto,
                json.dumps(articoli, ensure_ascii=False),
                tot["totale_scontato"],
                tot["saldo"],
                base_name,
                now,
                pid,
            ),
        )
        db.commit()
        new_id = int(pid)
    else:
        cur = db.execute(
            """INSERT INTO preventivi
               (cliente, data, consegna, pagamento, iva, sconto, acconto,
                articoli_json, totale, saldo, nome_file, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                cliente,
                payload["data"],
                payload["consegna"],
                payload["pagamento"],
                iva,
                sconto,
                acconto,
                json.dumps(articoli, ensure_ascii=False),
                tot["totale_scontato"],
                tot["saldo"],
                base_name,
                now,
                now,
            ),
        )
        db.commit()
        new_id = cur.lastrowid

    sync_file(prev_path, f"files/preventivi/{base_name}.prev")
    sync_file(pdf_path, f"files/pdf/{base_name}.pdf")
    sync_db()
    drive_ok = drive_store.enabled() and not drive_store.last_error()

    return jsonify(
        {
            "ok": True,
            "id": new_id,
            "file": base_name,
            "prev": f"preventivi/{base_name}.prev",
            "pdf": f"pdf/{base_name}.pdf",
            "totali": tot,
            "drive": drive_store.enabled(),
            "drive_ok": drive_ok,
            "drive_error": drive_store.last_error(),
        }
    )


@app.route("/api/preventivi/<int:pid>", methods=["GET", "DELETE"])
@login_required
def api_preventivo(pid: int):
    db = get_db()
    if request.method == "DELETE":
        row = db.execute("SELECT nome_file FROM preventivi WHERE id=?", (pid,)).fetchone()
        db.execute("DELETE FROM preventivi WHERE id=?", (pid,))
        db.commit()
        if row and row["nome_file"]:
            for sub, ext in (("preventivi", ".prev"), ("pdf", ".pdf")):
                p = FILES_DIR / sub / f"{row['nome_file']}{ext}"
                if p.exists():
                    p.unlink()
                sync_delete(f"files/{sub}/{row['nome_file']}{ext}")
        sync_db()
        return jsonify({"ok": True})

    row = db.execute("SELECT * FROM preventivi WHERE id=?", (pid,)).fetchone()
    if not row:
        return jsonify({"error": "Non trovato"}), 404
    d = dict(row)
    d["articoli"] = json.loads(d["articoli_json"])
    return jsonify(d)


@app.route("/api/pdf", methods=["POST"])
@login_required
def api_pdf_preview():
    """Genera PDF al volo senza salvare (download immediato)."""
    data = request.get_json(force=True)
    articoli = data.get("articoli") or []
    if not articoli:
        return jsonify({"error": "Nessun articolo"}), 400
    for a in articoli:
        a["qty"] = int(a["qty"])
        a["prezzo"] = float(str(a["prezzo"]).replace(",", "."))
        a["totale"] = a["qty"] * a["prezzo"]
    payload = {
        "cliente": data.get("cliente") or "",
        "data": data.get("data") or "",
        "consegna": data.get("consegna") or "",
        "pagamento": data.get("pagamento") or "",
        "iva": float(str(data.get("iva", 0)).replace(",", ".") or 0),
        "sconto": float(str(data.get("sconto", 0)).replace(",", ".") or 0),
        "acconto": float(str(data.get("acconto", 0)).replace(",", ".") or 0),
        "articoli": articoli,
    }
    pdf_bytes = genera_pdf_bytes(payload, get_azienda())
    nome = f"preventivo_{slugify(payload['cliente'] or 'tmp')}.pdf"
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=nome,
    )


# ---------- File manager ----------
@app.route("/files/download")
@login_required
def files_download():
    folder = request.args.get("folder", "")
    name = request.args.get("name", "")
    target = safe_rel_path(folder, name)
    if not target or not target.is_file():
        flash("File non trovato.", "error")
        return redirect(url_for("files_page", folder=folder or "preventivi"))
    return send_file(target, as_attachment=True)


@app.route("/files/delete", methods=["POST"])
@login_required
def files_delete():
    folder = request.form.get("folder", "")
    name = request.form.get("name", "")
    target = safe_rel_path(folder, name)
    if target and target.is_file():
        target.unlink()
        sync_delete(f"files/{folder}/{name}" if folder else name)
        flash(f"Eliminato: {name}", "ok")
    else:
        flash("File non trovato.", "error")
    return redirect(url_for("files_page", folder=folder or "preventivi"))


@app.route("/files/upload", methods=["POST"])
@login_required
def files_upload():
    folder = request.form.get("folder", "preventivi")
    if folder not in ("preventivi", "pdf"):
        folder = "preventivi"
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Nessun file selezionato.", "error")
        return redirect(url_for("files_page", folder=folder))
    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD:
        flash("Tipo file non consentito.", "error")
        return redirect(url_for("files_page", folder=folder))
    name = secure_filename(f.filename)
    dest = FILES_DIR / folder / name
    f.save(dest)
    sync_file(dest, f"files/{folder}/{name}")
    flash(f"Caricato: {name}", "ok")
    return redirect(url_for("files_page", folder=folder))


@app.route("/files/open-prev")
@login_required
def open_prev():
    """Apre un .prev nel compilatore."""
    folder = request.args.get("folder", "preventivi")
    name = request.args.get("name", "")
    target = safe_rel_path(folder, name)
    if not target or not target.is_file() or target.suffix.lower() != ".prev":
        flash("Preventivo non valido.", "error")
        return redirect(url_for("files_page", folder=folder))
    data = json.loads(target.read_text(encoding="utf-8"))
    session["draft_preventivo"] = data
    return redirect(url_for("index", draft=1))


@app.route("/api/draft")
@login_required
def api_draft():
    draft = session.pop("draft_preventivo", None)
    return jsonify(draft or {})


@app.route("/logo")
@login_required
def serve_logo():
    az = get_azienda()
    logo = az.get("logo_path") or ""
    if not logo:
        return ("", 404)
    path = BASE_DIR / logo
    if not path.exists():
        return ("", 404)
    return send_file(path)


@app.context_processor
def inject_globals():
    try:
        az = get_azienda()
    except Exception:
        az = {}
    return {
        "azienda": az,
        "has_password": bool(APP_PASSWORD),
        "drive_enabled": drive_store.enabled(),
    }


def bootstrap() -> None:
    ensure_dirs()
    if drive_store.enabled():
        stats = drive_store.pull_data_tree(DATA_DIR)
        print(f"[Drive] sync avvio: db={stats['db']} files={stats['files']}")
    init_db()


bootstrap()

if __name__ == "__main__":
    # host 0.0.0.0 = raggiungibile da altri PC/telefoni sulla stessa rete Wi‑Fi
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
