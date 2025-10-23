from flask import Flask, request, send_file, jsonify
from sqlalchemy import inspect
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4, landscape
from flask_cors import CORS
from num2words import num2words
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from flask_mail import Mail, Message
import string
import re
import random
import threading
import socket

app = Flask(__name__)
CORS(app)

# --- Base de données ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'postgresql://userdb:9Hk2HqdJhemKcTBZNg37mab0t4HO73uP@dpg-d3t7rubipnbc738gl82g-a/chequedb'
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# --- Email (Gmail) ---
app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", "587"))
app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
app.config["MAIL_USE_SSL"] = os.environ.get("MAIL_USE_SSL", "false").lower() == "true"
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "cheque1manager@gmail.com")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "dzxo rclj ujfx rehm")  # à remplacer par env en prod
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER", app.config["MAIL_USERNAME"])

# Eviter les blocages réseau prolongés (SMTP inaccessible)
socket.setdefaulttimeout(5)

db = SQLAlchemy(app)
mail = Mail(app)

# --- Modèles ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    mac_address = db.Column(db.String(100))
    password = db.Column(db.String(200), nullable=True)    
    cheques = db.relationship("Cheque", backref="user", lazy=True)

class Cheque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    banque = db.Column(db.String(120), nullable=False)
    a_lordre = db.Column(db.String(200))
    montant = db.Column(db.String(50))
    montant_lettres = db.Column(db.Text)
    date = db.Column(db.String(50))
    lieu = db.Column(db.String(100))
    cause = db.Column(db.String(200))
    tireur = db.Column(db.String(200))
    date_echeance = db.Column(db.String(50))
    date_creation = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

CHEQUE_MODELES = {
    "CIH Bank": {
        "positions": {"a_lordre": [100, 50], "montant_num": [200, 68.8], "montant_lettres": [130, 62], "lieu": [160, 42], "date": [200, 42]},
        "font": "Helvetica-Bold", "font_size": 12
    },
    "BMCI": {
        "positions": {"a_lordre": [105, 51], "montant_num": [202, 69], "montant_lettres": [132, 63], "lieu": [162, 43], "date": [202, 43]},
        "font": "Helvetica-Bold", "font_size": 12
    },
    "Al Barid Bank": {
        "positions": {"a_lordre": [98, 49], "montant_num": [198, 68], "montant_lettres": [128, 61], "lieu": [158, 41], "date": [198, 41]},
        "font": "Helvetica-Bold", "font_size": 12
    },
    "Crédit Agricole du Maroc": {
        "positions": {"a_lordre": [100, 50], "montant_num": [200, 68.8], "montant_lettres": [130, 62], "lieu": [160, 42], "date": [200, 42]},
        "font": "Helvetica-Bold", "font_size": 12
    },
    "Crédit du Maroc": {
        "positions": {"a_lordre": [102, 50.5], "montant_num": [201, 69], "montant_lettres": [131, 62], "lieu": [160, 42], "date": [201, 42]},
        "font": "Helvetica-Bold", "font_size": 12
    },
    "Banque Populaire": {
        "positions": {"a_lordre": [99, 49.5], "montant_num": [199, 68.5], "montant_lettres": [129, 61.5], "lieu": [159, 41.5], "date": [199, 41.5]},
        "font": "Helvetica-Bold", "font_size": 12
    },
    "Société Générale": {
        "positions": {"a_lordre": [101, 50], "montant_num": [200, 68.8], "montant_lettres": [130, 62], "lieu": [160, 42], "date": [200, 42]},
        "font": "Helvetica-Bold", "font_size": 12
    },
    "Attijariwafa Bank": {
        "positions": {"a_lordre": [100, 50], "montant_num": [200, 68.8], "montant_lettres": [130, 62], "lieu": [160, 42], "date": [200, 42]},
        "font": "Helvetica-Bold", "font_size": 12
    },
}

CHEQUE_MODLES_LETTRES = {
    "lettre_ATTIJARI_WAFA_BANK": {
        "positions": {
            "montant_num": [218, 84],
            "montant_lettres": [200, 66],
            "a_lordre": [130, 77],
            "lieu": [126, 68],
            "date": [147, 68],
            "cause": [130, 59],
            "tireur": [80, 74],
            "date_echeance": [218, 96],
        },
        "font": "Helvetica-Bold",
        "font_size": 10
    },

    "lettre_Bank_Of_Africa": {
        "positions": {
            "montant_num": [218, 59],
            "montant_lettres": [200, 50],
            "a_lordre": [130, 75],
            "lieu": [128, 67],
            "date": [149, 67],
            "cause": [130, 60],
            "tireur": [80, 73],
            "date_echeance": [218, 68],
        },
        "font": "Helvetica-Bold",
        "font_size": 10
    },

    "lettre_BmCE": {
        "positions": {
            "montant_num": [218, 60],
            "montant_lettres": [200, 48],
            "a_lordre": [130, 77],
            "lieu": [128, 68],
            "date": [149, 68],
            "cause": [130, 59],
            "tireur": [80, 70],
            "date_echeance": [218, 69],
        },
        "font": "Helvetica-Bold",
        "font_size": 10
    },

    "lettre_BMCI": {
        "positions": {
            "montant_num": [218, 87],
            "montant_lettres": [200, 67],
            "a_lordre": [149, 74],
            "lieu": [129, 65],
            "date": [152, 65],
            "cause": [130, 56],
            "tireur": [80, 70],
            "date_echeance": [218, 97.5],
        },
        "font": "Helvetica-Bold",
        "font_size": 10
    },

    "lettre_CREDIT_AGRICOLE_DU_MAROC": {
        "positions": {
            "montant_num": [218, 87],
            "montant_lettres": [200, 68],
            "a_lordre": [130, 78],
            "lieu": [127, 68],
            "date": [148, 68],
            "cause": [130, 59],
            "tireur": [80, 70],
            "date_echeance": [218, 98],
        },
        "font": "Helvetica-Bold",
        "font_size": 10
    },
    

    "lettre_CREDIT_DU_MAROC": {
        "positions": {
            "montant_num": [218, 91],
            "montant_lettres": [200, 70],
            "a_lordre": [130, 80],
            "lieu": [128, 71],
            "date": [149, 71],
            "cause": [130, 61],
            "tireur": [80, 76],
            "date_echeance": [218, 102]
        },
        "font": "Helvetica-Bold",
        "font_size": 10
    },
    
    "lettre_POPULAIRE": {
        "positions": {
            "montant_num": [218, 90],
            "montant_lettres": [202, 64],
            "a_lordre": [138, 77],
            "lieu": [130, 68],
            "date": [150, 68],
            "cause": [130, 61],
            "tireur": [80, 72],
            "date_echeance": [218, 100],
        },
        "font": "Helvetica-Bold",
        "font_size": 10
    },
    "lettre_SOCIETE_GENERALE": {
        "positions": {
            "montant_num": [218, 90],
            "montant_lettres": [200, 68],
            "a_lordre": [130, 80],
            "lieu": [126, 70],
            "date": [147, 70],
            "cause": [130, 60],
            "tireur": [80, 75],
            "date_echeance": [218, 99],
        },
        "font": "Helvetica-Bold",
        "font_size": 10
    }
}

@app.route("/api/to_words", methods=["POST"])
def to_words():
    data = request.get_json()
    montant = data.get("montant")
    try:
        montant = float(montant)
    except (TypeError, ValueError):
        return jsonify({"error": "Montant invalide"}), 400
    montant_lettres = num2words(montant, lang="fr").replace("virgule", "et") + " dirhams"
    return jsonify({"montant_lettres": montant_lettres})
EMAIL_REGEX = re.compile(r"^[^@]+@[^@]+\.[^@]+$")
MAC_REGEX = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")

def normalize_mac(mac: str) -> str:
    return mac.strip().replace("-", ":").upper()

def generate_password(mac: str, length: int = 10) -> str:
    # Exemple: mot de passe pseudo-aléatoire basé sur MAC + entropie
    # Ici on ignore volontairement la MAC pour la sécurité et on génère un vrai random
    chars = string.ascii_letters + string.digits
    return "".join(random.SystemRandom().choice(chars) for _ in range(length))

def _send_signup_email_sync(recipient_email: str, username: str, password: str):
    subject = "Bienvenue sur notre plateforme"
    body = (
        f"Bonjour {username},\n\n"
        f"Votre compte a été créé avec succès.\n"
        f"Votre identifiant : {recipient_email}\n"
        f"Votre mot de passe sécurisé : {password}\n\n"
        "Merci de votre inscription !"
    )
    msg = Message(
        subject=subject,
        recipients=[recipient_email],
        body=body,
        sender=app.config.get("MAIL_DEFAULT_SENDER", app.config.get("MAIL_USERNAME")),
    )
    # Utiliser un app_context car on est possiblement sur un thread
    with app.app_context():
        mail.send(msg)

def send_signup_email_async(recipient_email: str, username: str, password: str):
    t = threading.Thread(
        target=_send_signup_email_sync,
        args=(recipient_email, username, password),
        daemon=True
    )
    t.start()

# --- Route signup ---
@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    mac_address = data.get("mac_address")

    if not email or not mac_address:
        return jsonify({"error": "Email et adresse MAC sont requis"}), 400

    if not EMAIL_REGEX.match(email):
        return jsonify({"error": "Format d'email invalide"}), 400

    mac_address = normalize_mac(mac_address)
    if not MAC_REGEX.match(mac_address):
        return jsonify({"error": "Adresse MAC invalide (format attendu: AA:BB:CC:DD:EE:FF)"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email déjà existant"}), 400

    if User.query.filter_by(mac_address=mac_address).first():
        return jsonify({"error": "Adresse MAC déjà enregistrée"}), 400

    # Username = tout avant @
    username = email.split("@")[0]

    # Générer mot de passe sécurisé
    password = generate_password(mac_address, length=12)

    # Créer utilisateur
    user = User(username=username, email=email, mac_address=mac_address, password=password)
    db.session.add(user)
    db.session.commit()

    try:
        send_signup_email_async(email, username, password)
    except Exception as e:
        app.logger.exception("Echec lancement envoi email: %s", e)
        # On ne bloque pas l'inscription pour un échec d'email

    return jsonify({"message": "Utilisateur inscrit avec succès", "user_id": user.id}), 201
 
@app.route("/api/cheque_pdf", methods=["POST"])
def cheque_pdf():
    data = request.json
    banque = data.get("banque")

    is_lettre = banque.startswith("lettre_")
    bank_entry = CHEQUE_MODELES.get(banque) if not is_lettre else CHEQUE_MODLES_LETTRES.get(banque)
    if not bank_entry:
        return jsonify({"error": f"Banque '{banque}' non trouvée."}), 404

    positions = bank_entry["positions"]
    font = bank_entry.get("font", "Helvetica-Bold")
    font_size = bank_entry.get("font_size", 12)

    a_lordre = data.get("a_lordre", "")
    montant = data.get("montant", "")
    montant_lettres = data.get("montant_lettres", "")
    date = data.get("date", "")
    lieu = data.get("lieu", "")
    cause = data.get("la_cause", "")
    tireur = data.get("le_tireur", "")
    date_echeance = data.get("date_echeance", "")

    if is_lettre:
        cheque_width = 200 * mm
        cheque_height = 104 * mm
        page_width, page_height = landscape(A4)
    else:
        cheque_width = 175 * mm
        cheque_height = 80 * mm
        page_width, page_height = landscape(A4)

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(page_width, page_height))
    c.setFont(font, font_size)

    x_offset = (page_width - cheque_width) / 50 - 50 * mm
    y_offset = page_height - cheque_height - 109 * mm

    def draw(field, text):
        if field in positions and text:
            x, y = positions[field]
            c.drawString(x_offset + x * mm, y_offset + y * mm, str(text))

    draw("a_lordre", a_lordre)
    draw("montant_num", f"{montant} DH" if montant else "")
    draw("montant_lettres", montant_lettres)
    draw("lieu", lieu)
    draw("date", date)

    if is_lettre:
        draw("cause", cause)
        draw("tireur", tireur)
        draw("date_echeance", date_echeance)

    c.showPage()
    c.save()
    buffer.seek(0)

    # 🔹 Enregistrer le chèque dans la base
    user_id = data.get("user_id")
    if user_id:
        user = User.query.get(user_id)
        if user:
            new_cheque = Cheque(
                banque=banque,
                a_lordre=a_lordre,
                montant=montant,
                montant_lettres=montant_lettres,
                date=date,
                lieu=lieu,
                cause=cause,
                tireur=tireur,
                date_echeance=date_echeance,
                user_id=user.id
            )
            db.session.add(new_cheque)
            db.session.commit()

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"cheque_{banque.replace(' ', '_')}.pdf"
    )


@app.route("/api/user/<int:user_id>/cheques", methods=["GET"])
def get_user_cheques(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "Utilisateur non trouvé"}), 404

    cheques = [
        {
            "id": c.id,
            "banque": c.banque,
            "a_lordre": c.a_lordre,
            "montant": c.montant,
            "date": c.date,
            "lieu": c.lieu,
            "cause": c.cause,
            "date_echeance": c.date_echeance,
            "date_creation": c.date_creation.strftime("%Y-%m-%d %H:%M")
        }
        for c in user.cheques
    ]

    return jsonify(cheques)


@app.route("/api/banques", methods=["GET"])
def get_banques():
    return jsonify(list(CHEQUE_MODELES.keys()) + list(CHEQUE_MODLES_LETTRES.keys()))


@app.route('/check_db')
def check_db():
    try:
        # Inspecteur pour lister les tables
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        # Vérifie si les tables User et Cheque existent
        required_tables = ['user', 'cheque']
        missing = [t for t in required_tables if t not in tables]

        if not missing:
            return jsonify({
                "status": "ok",
                "message": "Base PostgreSQL connectée et tables installées : " + ", ".join(required_tables),
                "tables_presentes": tables
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Tables manquantes : " + ", ".join(missing),
                "tables_presentes": tables
            })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


with app.app_context():
    db.create_all()
    
@app.route('/')
def home():
    return "Backend des chèques connecté à PostgreSQL Render !"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))