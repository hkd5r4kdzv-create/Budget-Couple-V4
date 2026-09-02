import os
import csv
import io
from datetime import date
from functools import wraps
import psycopg
from psycopg.rows import dict_row
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "CHANGE-ME")

DATABASE_URL = os.environ["DATABASE_URL"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
id BIGSERIAL PRIMARY KEY,
username TEXT UNIQUE NOT NULL,
password_hash TEXT NOT NULL,
display_name TEXT NOT NULL,
is_admin BOOLEAN NOT NULL DEFAULT FALSE,
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS settings (
id INTEGER PRIMARY KEY CHECK (id = 1),
person1 TEXT NOT NULL DEFAULT 'Nathan',
salary1 NUMERIC(12,2) NOT NULL DEFAULT 0,
person2 TEXT NOT NULL DEFAULT 'Angèle',
salary2 NUMERIC(12,2) NOT NULL DEFAULT 0,
savings_goal NUMERIC(12,2) NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS fixed_expenses (
id BIGSERIAL PRIMARY KEY,
name TEXT NOT NULL,
amount NUMERIC(12,2) NOT NULL CHECK(amount >= 0)
);
CREATE TABLE IF NOT EXISTS expenses (
id BIGSERIAL PRIMARY KEY,
category TEXT NOT NULL,
amount NUMERIC(12,2) NOT NULL CHECK(amount >= 0),
paid_by TEXT NOT NULL,
note TEXT NOT NULL DEFAULT '',
spent_on DATE NOT NULL,
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO settings(id) VALUES(1) ON CONFLICT DO NOTHING;
"""

def connect():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def init_db():
    with connect() as con:
        con.execute(SCHEMA)

init_db()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        if not session.get("is_admin"):
            flash("Accès réservé à l’administrateur.")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)
    return wrapped

@app.route("/health")
def health():
    with connect() as con:
        con.execute("SELECT 1")
    return "OK", 200

@app.route("/setup", methods=["GET","POST"])
def setup():
    with connect() as con:
        count = con.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    if count:
        return redirect(url_for("login"))
    if request.method == "POST":
        username = request.form["username"].strip()
        display_name = request.form["display_name"].strip()
        password = request.form["password"]
        if len(username) < 3 or len(password) < 8 or not display_name:
            flash("Nom : obligatoire. Identifiant : 3 caractères minimum. Mot de passe : 8 minimum.")
            return render_template("setup.html")
        try:
            with connect() as con:
                con.execute(
                    "INSERT INTO users(username,password_hash,display_name,is_admin) VALUES(%s,%s,%s,TRUE)",
                    (username, generate_password_hash(password), display_name)
                )
            return redirect(url_for("login"))
        except Exception:
            flash("Impossible de créer ce compte. Essayez un autre identifiant.")
            return render_template("setup.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        password_confirm = request.form.get("password_confirm", "")
        display_name = username
        if len(username) < 3:
            flash("L’identifiant doit contenir au moins 3 caractères.")
            return render_template("register.html")
        if len(password) < 8:
            flash("Le mot de passe doit contenir au moins 8 caractères.")
            return render_template("register.html")
        if password != password_confirm:
            flash("Les deux mots de passe ne correspondent pas.")
            return render_template("register.html")
        try:
            with connect() as con:
                con.execute(
                    "INSERT INTO users(username,password_hash,display_name,is_admin) VALUES(%s,%s,%s,FALSE)",
                    (username, generate_password_hash(password), display_name)
                )
            flash("Compte créé, tu peux te connecter.")
            return redirect(url_for("login"))
        except Exception:
            flash("Cet identifiant est déjà pris.")
            return render_template("register.html")

    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        with connect() as con:
            u = con.execute("SELECT * FROM users WHERE username=%s", (request.form["username"].strip(),)).fetchone()
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session.clear()
            session.update(user_id=u["id"], username=u["username"], display_name=u["display_name"], is_admin=u["is_admin"])
            return redirect(url_for("dashboard"))
        flash("Identifiant ou mot de passe incorrect.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    month = request.args.get("month") or date.today().strftime("%Y-%m")
    with connect() as con:
        s = con.execute("SELECT * FROM settings WHERE id=1").fetchone()
        fixed = con.execute("SELECT * FROM fixed_expenses ORDER BY id").fetchall()
        expenses = con.execute(
            "SELECT * FROM expenses WHERE to_char(spent_on,'YYYY-MM')=%s ORDER BY spent_on DESC,id DESC",
            (month,)
        ).fetchall()
    income = float(s["salary1"] + s["salary2"])
    fixed_total = sum(float(x["amount"]) for x in fixed)
    variable_total = sum(float(x["amount"]) for x in expenses)
    remaining = income - fixed_total - variable_total
    bycat = {}
    for x in expenses:
        bycat[x["category"]] = bycat.get(x["category"], 0) + float(x["amount"])
    paid1 = sum(float(x["amount"]) for x in expenses if x["paid_by"] == s["person1"])
    paid2 = sum(float(x["amount"]) for x in expenses if x["paid_by"] == s["person2"])
    return render_template("dashboard.html", s=s, month=month, fixed=fixed, expenses=expenses,
                           income=income, fixed_total=fixed_total, variable_total=variable_total, remaining=remaining,
                           bycat=bycat, paid1=paid1, paid2=paid2)

@app.post("/settings")
@login_required
def settings():
    f=request.form
    with connect() as con:
        con.execute("""UPDATE settings SET person1=%s,salary1=%s,person2=%s,salary2=%s,savings_goal=%s WHERE id=1""",
                    (f["person1"].strip(), float(f["salary1"] or 0), f["person2"].strip(),
                     float(f["salary2"] or 0), float(f["savings_goal"] or 0)))
    return redirect(url_for("dashboard"))

@app.post("/fixed/add")
@login_required
def fixed_add():
    with connect() as con:
        con.execute("INSERT INTO fixed_expenses(name,amount) VALUES(%s,%s)",
                    (request.form["name"].strip(), float(request.form["amount"] or 0)))
    return redirect(url_for("dashboard"))

@app.post("/fixed/delete/<int:item_id>")
@login_required
def fixed_delete(item_id):
    with connect() as con:
        con.execute("DELETE FROM fixed_expenses WHERE id=%s", (item_id,))
    return redirect(url_for("dashboard"))

@app.post("/expense/add")
@login_required
def expense_add():
    f=request.form
    with connect() as con:
        con.execute("""INSERT INTO expenses(category,amount,paid_by,note,spent_on)
                    VALUES(%s,%s,%s,%s,%s)""",
                    (f["category"], float(f["amount"] or 0), f["paid_by"],
                     f.get("note","").strip(), f["spent_on"]))
    return redirect(url_for("dashboard", month=f["spent_on"][:7]))

@app.post("/expense/delete/<int:item_id>")
@login_required
def expense_delete(item_id):
    with connect() as con:
        con.execute("DELETE FROM expenses WHERE id=%s", (item_id,))
    return redirect(url_for("dashboard"))

@app.route("/admin", methods=["GET","POST"])
@admin_required
def admin():
    if request.method == "POST":
        f=request.form
        if len(f["password"]) < 8:
            flash("Le mot de passe doit contenir au moins 8 caractères.")
        else:
            try:
                with connect() as con:
                    con.execute(
                        "INSERT INTO users(username,password_hash,display_name,is_admin) VALUES(%s,%s,%s,FALSE)",
                        (f["username"].strip(), generate_password_hash(f["password"]), f["display_name"].strip())
                    )
                flash("Compte créé.")
            except Exception:
                flash("Cet identifiant existe déjà.")
    with connect() as con:
        users=con.execute("SELECT id,username,display_name,is_admin FROM users ORDER BY id").fetchall()
    return render_template("admin.html", users=users)

@app.get("/admin/export/users.csv")
@admin_required
def export_users():
    with connect() as con:
        users = con.execute(
            "SELECT id,username,display_name,is_admin,created_at FROM users ORDER BY id"
        ).fetchall()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "identifiant", "nom_affiche", "admin", "cree_le"])
    for u in users:
        writer.writerow([u["id"], u["username"], u["display_name"], u["is_admin"], u["created_at"]])
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=utilisateurs.csv"},
    )

@app.get("/admin/export/expenses.csv")
@admin_required
def export_expenses():
    with connect() as con:
        expenses = con.execute(
            "SELECT id,category,amount,paid_by,note,spent_on,created_at FROM expenses ORDER BY spent_on DESC, id DESC"
        ).fetchall()
        fixed = con.execute(
            "SELECT id,name,amount FROM fixed_expenses ORDER BY id"
        ).fetchall()
        s = con.execute("SELECT * FROM settings WHERE id=1").fetchone()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["-- Revenus --"])
    writer.writerow(["personne", "revenu"])
    writer.writerow([s["person1"], s["salary1"]])
    writer.writerow([s["person2"], s["salary2"]])
    writer.writerow([])
    writer.writerow(["-- Charges fixes --"])
    writer.writerow(["id", "nom", "montant"])
    for f in fixed:
        writer.writerow([f["id"], f["name"], f["amount"]])
        writer.writerow([])
        writer.writerow(["-- Dépenses --"])
        writer.writerow(["id", "categorie", "montant", "paye_par", "note", "date", "cree_le"])
    for e in expenses:
        writer.writerow([e["id"], e["category"], e["amount"], e["paid_by"], e["note"], e["spent_on"], e["created_at"]])
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=depenses.csv"},
    )

@app.post("/admin/delete/<int:user_id>")
@admin_required
def admin_delete(user_id):
    if user_id == session["user_id"]:
        flash("Vous ne pouvez pas supprimer votre propre compte.")
    else:
        with connect() as con:
            con.execute("DELETE FROM users WHERE id=%s", (user_id,))
        flash("Compte supprimé.")
    return redirect(url_for("admin"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
