#!/usr/bin/env python3
"""Anonymous, shared Western Rodeo best-dressed voting site (Python stdlib only)."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
from http.cookies import SimpleCookie
import base64
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import time

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
DATA_DIR = Path(os.environ.get("DATA_DIR", str(ROOT / "data"))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "voting.sqlite3"
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "RodeoAdmin2026!")
SECURE_COOKIE = os.environ.get("SECURE_COOKIE", "0").lower() in ("1", "true", "yes")
MAX_BODY = 25 * 1024 * 1024


def connect_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def initialize_db():
    with connect_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS participants (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('masculino','femenino')),
            photo TEXT NOT NULL DEFAULT '',
            position INTEGER NOT NULL DEFAULT 0
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS votes (
            voter_hash TEXT PRIMARY KEY,
            male_id TEXT NOT NULL,
            male_name TEXT NOT NULL,
            female_id TEXT NOT NULL,
            female_name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )""")
        conn.commit()


def escape_json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "RodeoVote/1.0"

    # Do not write access logs; in particular, never log voters' IP addresses.
    def log_message(self, format, *args):
        return

    def _send(self, status, body=b"", content_type="text/plain; charset=utf-8", headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Cache-Control", "no-store")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, status, data, headers=None):
        self._send(status, escape_json_bytes(data), "application/json; charset=utf-8", headers)

    def _read_json(self):
        raw_len = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_len)
        except ValueError:
            raise ValueError("Tamaño de solicitud no válido.")
        if length < 0 or length > MAX_BODY:
            raise OverflowError("La solicitud es demasiado grande.")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("El contenido enviado no es JSON válido.")

    def _token(self, create=False):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            cookie = SimpleCookie()
        morsel = cookie.get("rodeo_voter")
        token = morsel.value if morsel else ""
        headers = None
        # Only accept URL-safe random tokens of the expected minimum length.
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,100}", token or ""):
            token = ""
        if not token and create:
            token = secrets.token_urlsafe(32)
            cookie_value = f"rodeo_voter={token}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax"
            if SECURE_COOKIE:
                cookie_value += "; Secure"
            headers = {"Set-Cookie": cookie_value}
        return token, headers

    def _admin_ok(self):
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header.split(" ", 1)[1], validate=True).decode("utf-8")
            username, password = decoded.split(":", 1)
        except Exception:
            return False
        return hmac.compare_digest(username, "admin") and hmac.compare_digest(password, ADMIN_PASSWORD)

    def _admin_required(self):
        path = urlparse(self.path).path
        if path == "/admin" or path.startswith("/api/admin"):
            if not self._admin_ok():
                self._send(401, b"Se requiere acceso de organizador.", headers={"WWW-Authenticate": 'Basic realm="Rodeo Admin", charset="UTF-8"'})
                return False
        return True

    def do_GET(self):
        path = urlparse(self.path).path
        if not self._admin_required():
            return

        if path in ("/", "/index.html"):
            return self._serve_file(PUBLIC / "index.html", "text/html; charset=utf-8")
        if path == "/admin":
            return self._serve_file(PUBLIC / "admin.html", "text/html; charset=utf-8")
        if path == "/api/state":
            token, headers = self._token(create=True)
            with connect_db() as conn:
                male = conn.execute("SELECT id,name,photo FROM participants WHERE category='masculino' ORDER BY position,name COLLATE NOCASE").fetchall()
                female = conn.execute("SELECT id,name,photo FROM participants WHERE category='femenino' ORDER BY position,name COLLATE NOCASE").fetchall()
                voted = bool(token and conn.execute("SELECT 1 FROM votes WHERE voter_hash=?", (hashlib.sha256(token.encode()).hexdigest(),)).fetchone())
            return self._json(200, {
                "male": [dict(row) for row in male],
                "female": [dict(row) for row in female],
                "voted": voted,
                "ready": bool(male and female)
            }, headers=headers)
        if path == "/api/admin/participants":
            with connect_db() as conn:
                rows = conn.execute("SELECT id,name,category,photo,position FROM participants ORDER BY category,position,name COLLATE NOCASE").fetchall()
            return self._json(200, [dict(row) for row in rows])
        if path == "/api/admin/status":
            with connect_db() as conn:
                votes = conn.execute("SELECT COUNT(*) AS n FROM votes").fetchone()["n"]
                male = conn.execute("SELECT COUNT(*) AS n FROM participants WHERE category='masculino'").fetchone()["n"]
                female = conn.execute("SELECT COUNT(*) AS n FROM participants WHERE category='femenino'").fetchone()["n"]
            return self._json(200, {"votes": votes, "male_count": male, "female_count": female})
        if path == "/api/admin/results":
            with connect_db() as conn:
                rows = conn.execute("SELECT male_name,female_name,created_at FROM votes ORDER BY created_at").fetchall()
            male_counts, female_counts = {}, {}
            for row in rows:
                male_counts[row["male_name"]] = male_counts.get(row["male_name"], 0) + 1
                female_counts[row["female_name"]] = female_counts.get(row["female_name"], 0) + 1
            return self._json(200, {
                "total": len(rows),
                "male": [{"name": n, "votes": v} for n, v in sorted(male_counts.items(), key=lambda item: (-item[1], item[0].casefold()))],
                "female": [{"name": n, "votes": v} for n, v in sorted(female_counts.items(), key=lambda item: (-item[1], item[0].casefold()))]
            })
        if path == "/api/admin/export.csv":
            with connect_db() as conn:
                rows = conn.execute("SELECT male_name,female_name,created_at FROM votes ORDER BY created_at").fetchall()
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(["Mejor vestido masculino", "Mejor vestida femenina", "Fecha de registro (UTC)"])
            for row in rows:
                writer.writerow([row["male_name"], row["female_name"], row["created_at"]])
            data = out.getvalue().encode("utf-8-sig")
            return self._send(200, data, "text/csv; charset=utf-8", {"Content-Disposition": 'attachment; filename="resultados-rodeo.csv"'})

        # Return no details for unknown paths.
        return self._json(404, {"error": "No encontrado."})

    def do_POST(self):
        path = urlparse(self.path).path
        if not self._admin_required():
            return
        try:
            if path == "/api/vote":
                return self._cast_vote()
            if path == "/api/admin/participants":
                return self._save_participants()
            if path == "/api/admin/reset":
                body = self._read_json()
                if not isinstance(body, dict) or body.get("confirm") != "REINICIAR":
                    return self._json(400, {"error": "Confirmación no válida."})
                with connect_db() as conn:
                    conn.execute("DELETE FROM votes")
                    conn.commit()
                return self._json(200, {"ok": True})
            return self._json(404, {"error": "No encontrado."})
        except OverflowError as exc:
            return self._json(413, {"error": str(exc)})
        except ValueError as exc:
            return self._json(400, {"error": str(exc)})
        except Exception:
            # Avoid returning internal database/system details to visitors.
            return self._json(500, {"error": "Ocurrió un error interno. Intenta de nuevo."})

    def _cast_vote(self):
        token, _ = self._token(create=False)
        if not token:
            return self._json(400, {"error": "No se pudo verificar este dispositivo. Recarga la página e intenta de nuevo."})
        body = self._read_json()
        if not isinstance(body, dict):
            raise ValueError("Voto no válido.")
        male_id, female_id = body.get("male_id"), body.get("female_id")
        if not isinstance(male_id, str) or not isinstance(female_id, str):
            raise ValueError("Selecciona una persona en cada categoría.")
        voter_hash = hashlib.sha256(token.encode()).hexdigest()
        with connect_db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM votes WHERE voter_hash=?", (voter_hash,)).fetchone():
                conn.rollback()
                return self._json(409, {"error": "Este dispositivo ya registró un voto."})
            male = conn.execute("SELECT id,name FROM participants WHERE id=? AND category='masculino'", (male_id,)).fetchone()
            female = conn.execute("SELECT id,name FROM participants WHERE id=? AND category='femenino'", (female_id,)).fetchone()
            if not male or not female:
                conn.rollback()
                return self._json(400, {"error": "Una de las opciones ya no está disponible. Actualiza la página e inténtalo de nuevo."})
            conn.execute("INSERT INTO votes(voter_hash,male_id,male_name,female_id,female_name) VALUES(?,?,?,?,?)",
                         (voter_hash, male["id"], male["name"], female["id"], female["name"]))
            conn.commit()
        return self._json(201, {"ok": True})

    def _save_participants(self):
        body = self._read_json()
        if not isinstance(body, list) or len(body) > 250:
            raise ValueError("La lista de participantes no es válida (máximo 250).")
        clean = []
        ids = set()
        for index, item in enumerate(body):
            if not isinstance(item, dict):
                raise ValueError("Hay un participante con datos no válidos.")
            pid = str(item.get("id", "")).strip() or secrets.token_hex(10)
            name = str(item.get("name", "")).strip()
            category = item.get("category")
            photo = str(item.get("photo", "")).strip()
            if pid in ids:
                raise ValueError("Hay identificadores duplicados. Recarga el panel e inténtalo de nuevo.")
            ids.add(pid)
            if not name or len(name) > 80:
                raise ValueError("Cada participante debe tener un nombre de 1 a 80 caracteres.")
            if category not in ("masculino", "femenino"):
                raise ValueError("Selecciona la categoría masculina o femenina para cada persona.")
            if len(photo) > 7 * 1024 * 1024:
                raise ValueError("Una fotografía supera el tamaño permitido de 7 MB.")
            if photo and not (photo.startswith("https://") or photo.startswith("http://") or re.match(r"^data:image/(png|jpeg|jpg|webp|gif);base64,[A-Za-z0-9+/=\r\n]+$", photo)):
                raise ValueError("Cada foto debe ser una imagen URL (http/https) o PNG, JPG, WEBP o GIF.")
            clean.append((pid, name, category, photo, index))
        if not any(p[2] == "masculino" for p in clean) or not any(p[2] == "femenino" for p in clean):
            raise ValueError("Agrega por lo menos una persona en cada categoría antes de guardar.")
        with connect_db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM participants")
            conn.executemany("INSERT INTO participants(id,name,category,photo,position) VALUES(?,?,?,?,?)", clean)
            conn.commit()
        return self._json(200, {"ok": True, "count": len(clean)})

    def _serve_file(self, path, content_type):
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return self._send(404, b"Archivo no encontrado.")
        return self._send(200, data, content_type)

    def do_HEAD(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._send(200, b"", "text/html; charset=utf-8")
        return self._send(404, b"")


def main():
    initialize_db()
    print("\nWestern Rodeo voting app")
    print(f"Abre: http://localhost:{PORT}")
    print(f"Panel organizador: http://localhost:{PORT}/admin")
    if "ADMIN_PASSWORD" not in os.environ:
        print("AVISO: clave temporal de admin: RodeoAdmin2026! — cámbiala antes de publicar en internet.")
    if not SECURE_COOKIE:
        print("AVISO: SECURE_COOKIE está desactivado; actívalo en hosting HTTPS público.")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
