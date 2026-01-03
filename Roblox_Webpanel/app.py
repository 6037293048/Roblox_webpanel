from flask import Flask, render_template, request, redirect
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timedelta
import secrets
import json

# =====================
# FLASK SETUP
# =====================
app = Flask(__name__)

# =====================
# DATABASE SETUP
# =====================
engine = create_engine("sqlite:///database.db")
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# =====================
# DATABASE MODELS
# =====================
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    password = Column(String)

class Panel(Base):
    __tablename__ = "panels"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String)
    panel_key = Column(String, unique=True)
    last_ping = Column(String, nullable=True)
    user = relationship("User")

class Command(Base):
    __tablename__ = "commands"
    id = Column(Integer, primary_key=True)
    panel_id = Column(Integer, ForeignKey("panels.id"))
    command = Column(String)
    executed = Column(Boolean, default=False)
    panel = relationship("Panel")

Base.metadata.create_all(engine)

# =====================
# HELPER
# =====================
def panel_connected(panel):
    if not panel.last_ping:
        return False
    return datetime.utcnow() - datetime.fromisoformat(panel.last_ping) < timedelta(seconds=10)

# =====================
# LOGIN / REGISTER
# =====================
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        db = SessionLocal()
        email = request.form["email"]
        password = request.form["password"]

        user = db.query(User).filter_by(email=email, password=password).first()
        if not user:
            user = User(email=email, password=password)
            db.add(user)
            db.commit()
            db.refresh(user)

        return redirect(f"/dashboard/{user.id}")

    return render_template("login.html")

# =====================
# DASHBOARD
# =====================
@app.route("/dashboard/<int:user_id>")
def dashboard(user_id):
    db = SessionLocal()
    panels = db.query(Panel).filter_by(user_id=user_id).all()
    return render_template("dashboard.html", panels=panels, user_id=user_id)

@app.route("/create_panel", methods=["POST"])
def create_panel():
    db = SessionLocal()
    user_id = request.form["user_id"]
    name = request.form["name"]

    panel = Panel(
        user_id=user_id,
        name=name,
        panel_key=secrets.token_urlsafe(24)
    )

    db.add(panel)
    db.commit()
    db.refresh(panel)

    return redirect(f"/panel/{panel.id}")

# =====================
# PANEL VIEW
# =====================
@app.route("/panel/<int:panel_id>")
def panel(panel_id):
    db = SessionLocal()
    panel = db.query(Panel).filter_by(id=panel_id).first()
    return render_template(
        "panel.html",
        panel=panel,
        connected=panel_connected(panel)
    )

# =====================
# API (ROBLOX)
# =====================
@app.route("/api/<panel_key>/connect", methods=["POST"])
def api_connect(panel_key):
    db = SessionLocal()
    panel = db.query(Panel).filter_by(panel_key=panel_key).first()
    if not panel:
        return {"error": "invalid key"}, 404

    panel.last_ping = datetime.utcnow().isoformat()
    db.commit()
    return {"status": "connected"}

@app.route("/api/<panel_key>/command", methods=["POST"])
def api_command(panel_key):
    db = SessionLocal()
    panel = db.query(Panel).filter_by(panel_key=panel_key).first()
    if not panel:
        return {"error": "invalid key"}, 404

    cmd = Command(panel_id=panel.id, command=request.form["command"])
    db.add(cmd)
    db.commit()
    return {"status": "queued"}

@app.route("/api/<panel_key>/command/next")
def api_next(panel_key):
    panel = Panel.query.filter_by(key=panel_key).first()
    if not panel:
        return jsonify({})

    cmd = Command.query.filter_by(panel_id=panel.id, done=False).first()
    if not cmd:
        return jsonify({})

    return jsonify({
        "id": cmd.id,
        "command": cmd.command
    })

@app.route("/api/<panel_key>/command/done", methods=["POST"])
def api_done(panel_key):
    try:
        panel = Panel.query.filter_by(key=panel_key).first()
        if not panel:
            return jsonify({"error": "invalid panel"}), 403

        data = request.get_json()
        if not data or "id" not in data:
            return jsonify({"error": "missing id"}), 400

        cmd = Command.query.filter_by(
            id=data["id"],
            panel_id=panel.id
        ).first()

        if not cmd:
            return jsonify({"error": "command not found"}), 404

        cmd.done = True
        db.session.commit()

        return jsonify({"ok": True})

    except Exception as e:
        print("❌ ERROR:", e)
        return jsonify({"error": "server error"}), 500

# =====================
# START SERVER
# =====================
if __name__ == "__main__":
    app.run(debug=True)
