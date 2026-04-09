
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Railway/containers: if SQLITE_PATH is defined use it.
# Fallback to local ./data for development.
DEFAULT_SQLITE_PATH = BASE_DIR / "data" / "turismo_tefe.db"
DATABASE = Path(os.environ.get("SQLITE_PATH", str(DEFAULT_SQLITE_PATH)))

STATUS_OPTIONS = ("Nova", "Em análise", "Planejada", "Concluída")

ATTRACTION_SEEDS = [
    {
        "title": "Praça Santa Teresa",
        "summary": "Ponto histórico de convivência e palco de eventos no coração de Tefé.",
        "content": (
            "A Praça Santa Teresa é um dos espaços mais tradicionais de Tefé. "
            "Ela concentra encontros da população, eventos culturais, celebrações religiosas "
            "e momentos importantes da vida social da cidade. Pela localização central e pela "
            "força simbólica que carrega, funciona como um cartão de visita para quem deseja "
            "entender a identidade urbana e cultural do município."
        ),
        "image": "img/praca-santa-teresa.jpg",
    },
    {
        "title": "Feira da Agricultura Familiar",
        "summary": "Sabores regionais, produção local e valorização da economia amazônica.",
        "content": (
            "A Feira da Agricultura Familiar fortalece produtores locais e aproxima visitantes "
            "da cultura alimentar da região. O espaço reúne frutas, verduras, farinhas, peixes, "
            "artesanato e outros produtos típicos, criando uma experiência rica para quem deseja "
            "conhecer a economia criativa e o cotidiano de Tefé."
        ),
        "image": "img/feira-agricultura.webp",
    },
    {
        "title": "Festa da Castanha",
        "summary": "Celebração cultural com música, culinária e tradições da região.",
        "content": (
            "A Festa da Castanha destaca a produção regional e valoriza saberes tradicionais "
            "ligados ao extrativismo amazônico. O evento costuma reunir apresentações culturais, "
            "pratos típicos, música e manifestações populares, reforçando o vínculo entre natureza, "
            "economia local e memória coletiva."
        ),
        "image": "img/festa-castanha.jpg",
    },
    {
        "title": "Arraial Folclórico",
        "summary": "Quadrilhas, bois-bumbás e manifestações populares que movimentam a cidade.",
        "content": (
            "O arraial é uma das celebrações que mais animam Tefé ao longo do ano. A programação "
            "combina danças típicas, apresentações folclóricas, comidas regionais e muito encontro "
            "comunitário. É um momento em que a cidade exibe com força sua criatividade, alegria e "
            "tradição popular."
        ),
        "image": "img/arraial-tefe.jpg",
    },
    {
        "title": "Encontro das Águas",
        "summary": "Paisagem amazônica marcante para passeios, contemplação e fotografia.",
        "content": (
            "O Encontro das Águas na região de Tefé é um espetáculo visual que chama atenção pela "
            "força da paisagem amazônica. A experiência é ideal para contemplação, registro fotográfico "
            "e passeios guiados, tornando-se um ponto de grande interesse turístico e educativo."
        ),
        "image": "img/encontro-aguas.jpg",
    },
    {
        "title": "Passeios de Barco",
        "summary": "Vivência com a natureza, comunidades ribeirinhas e os igarapés da região.",
        "content": (
            "Os passeios de barco permitem um contato mais direto com rios, lagos, comunidades "
            "ribeirinhas e cenários naturais da região. É uma atividade que combina lazer, observação "
            "da paisagem e aproximação com o modo de vida amazônico, ampliando a experiência do visitante."
        ),
        "image": "img/passeio-barco.jpg",
    },
]


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(TEMPLATES_DIR),
        static_folder=str(STATIC_DIR),
        static_url_path="/static",
    )

    # In production, set SECRET_KEY in Railway variables.
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    ensure_runtime_dirs()

    @app.teardown_appcontext
    def close_db(_: object | None) -> None:
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.template_filter("datetime_br")
    def datetime_br(value: str | None) -> str:
        return format_datetime(value)

    @app.template_filter("datetime_short")
    def datetime_short(value: str | None) -> str:
        parsed = parse_datetime(value)
        if not parsed:
            return "-"
        return parsed.strftime("%d/%m/%Y")

    @app.context_processor
    def inject_user() -> dict[str, Any]:
        return {
            "current_user": {
                "id": session.get("user_id"),
                "name": session.get("name"),
                "role": session.get("role"),
            }
        }

    @app.route("/health")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @app.route("/assets/<path:filename>")
    def asset_file(filename: str):
        target = BASE_DIR / filename
        if not target.exists():
            abort(404)
        return send_from_directory(BASE_DIR, filename)

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory(BASE_DIR, "Brasão.de.Tefé.png")

    @app.route("/")
    def home():
        return render_template("index.html", attractions=fetch_attractions(limit=3))

    @app.route("/atracoes")
    def attractions():
        return render_template("attractions.html", attractions=fetch_attractions())

    @app.route("/atracoes/<int:attraction_id>")
    def attraction_detail(attraction_id: int):
        attraction = get_attraction_or_404(attraction_id)
        return render_template("attraction_detail.html", attraction=attraction)

    @app.route("/sobre")
    def about():
        return render_template("about.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            username = request.form.get("username", "").strip().lower()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            if not all([name, username, email, password]):
                flash("Preencha todos os campos para criar a conta.", "error")
                return render_template("register.html")

            db = get_db()
            exists = db.execute(
                "SELECT id FROM users WHERE username = ? OR email = ?",
                (username, email),
            ).fetchone()

            if exists:
                flash("Esse usuário ou e-mail já está cadastrado.", "error")
                return render_template("register.html")

            db.execute(
                """
                INSERT INTO users (name, username, email, password_hash, role)
                VALUES (?, ?, ?, ?, 'user')
                """,
                (name, username, email, generate_password_hash(password)),
            )
            db.commit()
            flash("Conta criada com sucesso. Agora é só entrar.", "success")
            return redirect(url_for("login"))

        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            login_value = request.form.get("login", "").strip().lower()
            password = request.form.get("password", "")

            user = get_db().execute(
                "SELECT * FROM users WHERE username = ? OR email = ?",
                (login_value, login_value),
            ).fetchone()

            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session.update(
                    {"user_id": user["id"], "name": user["name"], "role": user["role"]}
                )
                flash(f"Bem-vindo, {user['name']}!", "success")
                if user["role"] == "admin":
                    return redirect(url_for("admin_dashboard"))
                return redirect(url_for("user_dashboard"))

            flash("Credenciais inválidas. Tente novamente.", "error")

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Sessão encerrada com sucesso.", "info")
        return redirect(url_for("home"))

    @app.route("/painel", methods=["GET", "POST"])
    @login_required
    @role_required("user")
    def user_dashboard():
        db = get_db()
        edit_id = request.args.get("edit", type=int)

        if request.method == "POST":
            action = request.form.get("action", "create")
            title = request.form.get("title", "").strip()
            message = request.form.get("message", "").strip()

            if action == "create" and title and message:
                db.execute(
                    """
                    INSERT INTO suggestions (user_id, title, message)
                    VALUES (?, ?, ?)
                    """,
                    (session["user_id"], title, message),
                )
                db.commit()
                flash("Sugestão enviada para a administração.", "success")
                return redirect(url_for("user_dashboard"))

            if action == "update":
                suggestion_id = request.form.get("suggestion_id", type=int)
                suggestion = get_suggestion_or_404(suggestion_id or 0)
                if suggestion["user_id"] != session["user_id"]:
                    abort(403)
                if title and message:
                    db.execute(
                        """
                        UPDATE suggestions
                        SET title = ?, message = ?, status = 'Em análise'
                        WHERE id = ?
                        """,
                        (title, message, suggestion_id),
                    )
                    db.commit()
                    flash("Sugestão atualizada com sucesso.", "success")
                    return redirect(url_for("user_dashboard"))

            flash("Escreva um título e uma mensagem para enviar a sugestão.", "error")

        suggestions = db.execute(
            """
            SELECT id, title, message, status, created_at
            FROM suggestions
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (session["user_id"],),
        ).fetchall()

        suggestion_in_edit = None
        if edit_id:
            suggestion_in_edit = db.execute(
                """
                SELECT id, title, message, status, created_at
                FROM suggestions
                WHERE id = ? AND user_id = ?
                """,
                (edit_id, session["user_id"]),
            ).fetchone()

        return render_template(
            "dashboard_user.html",
            suggestions=suggestions,
            suggestion_in_edit=suggestion_in_edit,
        )

    @app.post("/painel/sugestoes/<int:suggestion_id>/excluir")
    @login_required
    @role_required("user")
    def delete_suggestion(suggestion_id: int):
        suggestion = get_suggestion_or_404(suggestion_id)
        if suggestion["user_id"] != session["user_id"]:
            abort(403)
        get_db().execute("DELETE FROM suggestions WHERE id = ?", (suggestion_id,))
        get_db().commit()
        flash("Sugestão excluída.", "info")
        return redirect(url_for("user_dashboard"))

    @app.route("/admin", methods=["GET", "POST"])
    @login_required
    @role_required("admin")
    def admin_dashboard():
        db = get_db()
        edit_attraction_id = request.args.get("editar_atracao", type=int)

        if request.method == "POST":
            action = request.form.get("action", "create_attraction")
            title = request.form.get("title", "").strip()
            summary = request.form.get("summary", "").strip()
            content = request.form.get("content", "").strip()
            image = request.form.get("image", "").strip()

            if action == "create_attraction" and not all([title, summary, content, image]):
                flash("Preencha título, resumo, texto completo e imagem.", "error")
                return redirect(url_for("admin_dashboard"))

            if action == "create_attraction":
                exists = db.execute(
                    "SELECT id FROM attractions WHERE title = ?",
                    (title,),
                ).fetchone()
                if exists:
                    flash("Já existe uma atração com esse título.", "error")
                    return redirect(url_for("admin_dashboard"))

                db.execute(
                    """
                    INSERT INTO attractions (title, summary, content, image, created_by)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (title, summary, content, image, session["user_id"]),
                )
                db.commit()
                flash("Atração cadastrada com sucesso.", "success")
                return redirect(url_for("admin_dashboard"))

            if action == "update_attraction":
                attraction_id = request.form.get("attraction_id", type=int)
                if not attraction_id:
                    abort(400)
                if not all([title, summary, content, image]):
                    flash("Preencha todos os campos para atualizar a atração.", "error")
                    return redirect(url_for("admin_dashboard", editar_atracao=attraction_id))

                exists = db.execute(
                    "SELECT id FROM attractions WHERE title = ? AND id != ?",
                    (title, attraction_id),
                ).fetchone()
                if exists:
                    flash("Já existe outra atração com esse título.", "error")
                    return redirect(url_for("admin_dashboard", editar_atracao=attraction_id))

                db.execute(
                    """
                    UPDATE attractions
                    SET title = ?, summary = ?, content = ?, image = ?
                    WHERE id = ?
                    """,
                    (title, summary, content, image, attraction_id),
                )
                db.commit()
                flash("Atração atualizada com sucesso.", "success")
                return redirect(url_for("admin_dashboard"))

            if action == "update_suggestion_status":
                suggestion_id = request.form.get("suggestion_id", type=int)
                status = request.form.get("status", "").strip()
                if status not in STATUS_OPTIONS:
                    flash("Escolha um status válido para a sugestão.", "error")
                    return redirect(url_for("admin_dashboard"))
                db.execute(
                    "UPDATE suggestions SET status = ? WHERE id = ?",
                    (status, suggestion_id),
                )
                db.commit()
                flash("Status da sugestão atualizado.", "success")
                return redirect(url_for("admin_dashboard"))

        users = db.execute(
            """
            SELECT id, name, username, email, role, created_at
            FROM users
            ORDER BY created_at DESC
            """
        ).fetchall()
        suggestions = db.execute(
            """
            SELECT s.id, s.title, s.message, s.status, s.created_at, u.name
            FROM suggestions s
            JOIN users u ON u.id = s.user_id
            ORDER BY s.created_at DESC, s.id DESC
            """
        ).fetchall()
        attractions = fetch_attractions()
        attraction_in_edit = None
        if edit_attraction_id:
            attraction_in_edit = get_attraction_or_404(edit_attraction_id)

        stats = {
            "users": db.execute(
                "SELECT COUNT(*) AS total FROM users WHERE role = 'user'"
            ).fetchone()["total"],
            "admins": db.execute(
                "SELECT COUNT(*) AS total FROM users WHERE role = 'admin'"
            ).fetchone()["total"],
            "suggestions": db.execute(
                "SELECT COUNT(*) AS total FROM suggestions"
            ).fetchone()["total"],
            "attractions": db.execute(
                "SELECT COUNT(*) AS total FROM attractions"
            ).fetchone()["total"],
        }

        return render_template(
            "dashboard_admin.html",
            users=users,
            suggestions=suggestions,
            attractions=attractions,
            attraction_in_edit=attraction_in_edit,
            stats=stats,
            status_options=STATUS_OPTIONS,
        )

    @app.post("/admin/atracoes/<int:attraction_id>/excluir")
    @login_required
    @role_required("admin")
    def delete_attraction(attraction_id: int):
        get_attraction_or_404(attraction_id)
        get_db().execute("DELETE FROM attractions WHERE id = ?", (attraction_id,))
        get_db().commit()
        flash("Atração removida do portal.", "info")
        return redirect(url_for("admin_dashboard"))

    @app.post("/admin/sugestoes/<int:suggestion_id>/excluir")
    @login_required
    @role_required("admin")
    def delete_suggestion_admin(suggestion_id: int):
        get_suggestion_or_404(suggestion_id)
        get_db().execute("DELETE FROM suggestions WHERE id = ?", (suggestion_id,))
        get_db().commit()
        flash("Sugestão removida.", "info")
        return redirect(url_for("admin_dashboard"))

    register_error_handlers(app)

    with app.app_context():
        init_db()

    return app


def ensure_runtime_dirs() -> None:
    DATABASE.parent.mkdir(parents=True, exist_ok=True)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")

    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Nova',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS attractions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL UNIQUE,
            summary TEXT NOT NULL,
            content TEXT NOT NULL,
            image TEXT NOT NULL,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users (id) ON DELETE SET NULL
        );
        """
    )

    ensure_column(db, "attractions", "summary", "TEXT NOT NULL DEFAULT ''")
    ensure_column(db, "attractions", "content", "TEXT NOT NULL DEFAULT ''")
    ensure_column(db, "attractions", "image", "TEXT NOT NULL DEFAULT 'img/encontro-aguas.jpg'")
    ensure_column(db, "attractions", "created_by", "INTEGER")
    ensure_column(db, "attractions", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    seeds = [
        ("Administrador Tefé", "admin", "admin@tefe.com", "admin123", "admin"),
        ("Visitante Demo", "visitante", "visitante@tefe.com", "123456", "user"),
    ]

    for name, username, email, password, role in seeds:
        existing = db.execute(
            "SELECT id FROM users WHERE username = ? OR email = ?",
            (username, email),
        ).fetchone()
        if not existing:
            db.execute(
                """
                INSERT INTO users (name, username, email, password_hash, role)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, username, email, generate_password_hash(password), role),
            )

    admin_user = db.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    demo_user = db.execute("SELECT id FROM users WHERE username = 'visitante'").fetchone()

    for attraction in ATTRACTION_SEEDS:
        existing = db.execute(
            "SELECT id FROM attractions WHERE title = ?",
            (attraction["title"],),
        ).fetchone()
        if not existing:
            db.execute(
                """
                INSERT INTO attractions (title, summary, content, image, created_by)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    attraction["title"],
                    attraction["summary"],
                    attraction["content"],
                    attraction["image"],
                    admin_user["id"] if admin_user else None,
                ),
            )

    if demo_user:
        count = db.execute(
            "SELECT COUNT(*) AS total FROM suggestions WHERE user_id = ?",
            (demo_user["id"],),
        ).fetchone()["total"]
        if count == 0:
            db.executemany(
                """
                INSERT INTO suggestions (user_id, title, message, status)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        demo_user["id"],
                        "Roteiro gastronômico",
                        "Seria legal destacar melhor comidas típicas e feiras de fim de semana.",
                        "Em análise",
                    ),
                    (
                        demo_user["id"],
                        "Passeio de barco",
                        "Um mapa com pontos de saída para os passeios ajudaria bastante.",
                        "Nova",
                    ),
                ],
            )

    db.commit()
    db.close()


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def format_datetime(value: str | None) -> str:
    parsed = parse_datetime(value)
    if not parsed:
        return "-"
    return parsed.strftime("%d/%m/%Y às %H:%M")


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            flash("Faça login para acessar essa área.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped_view


def role_required(role: str):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if session.get("role") != role:
                flash("Você não tem permissão para acessar essa área.", "error")
                if session.get("role") == "admin":
                    return redirect(url_for("admin_dashboard"))
                if session.get("role") == "user":
                    return redirect(url_for("user_dashboard"))
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped_view

    return decorator


def get_suggestion_or_404(suggestion_id: int) -> sqlite3.Row:
    suggestion = get_db().execute(
        """
        SELECT s.*, u.name
        FROM suggestions s
        JOIN users u ON u.id = s.user_id
        WHERE s.id = ?
        """,
        (suggestion_id,),
    ).fetchone()
    if suggestion is None:
        abort(404)
    return suggestion


def get_attraction_or_404(attraction_id: int) -> sqlite3.Row:
    attraction = get_db().execute(
        """
        SELECT id, title, summary, content, image, created_at
        FROM attractions
        WHERE id = ?
        """,
        (attraction_id,),
    ).fetchone()
    if attraction is None:
        abort(404)
    return attraction


def fetch_attractions(limit: int | None = None) -> list[sqlite3.Row]:
    query = """
        SELECT id, title, summary, content, image, created_at
        FROM attractions
        ORDER BY created_at DESC, id DESC
    """
    if limit:
        query += " LIMIT ?"
        return get_db().execute(query, (limit,)).fetchall()
    return get_db().execute(query).fetchall()


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(_: Exception):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def internal_error(_: Exception):
        return render_template("500.html"), 500


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
