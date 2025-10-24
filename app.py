from flask import Flask, request, send_file, jsonify , session, make_response
from sqlalchemy import inspect
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4, landscape
from flask_cors import CORS
from num2words import num2words
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
import os
from flask_mail import Mail, Message
import string
import re
import random

app = Flask(__name__)
CORS(app, supports_credentials=True)


# --- Base de données ---
SERVER_DB_URL = os.environ.get(
    'DATABASE_URL','postgresql://userdb:qt1AHFUOLr83TsI5uriLhpm5tID4QKVU@dpg-d3tc1ov5r7bs73emkcv0-a/cheque_manager_db_6qiw'
)
LOCAL_DB_PATH = os.path.join(os.path.dirname(__file__), "local_data.db")

app.config['SQLALCHEMY_BINDS'] = {
    'server': SERVER_DB_URL,
    'local': f"sqlite:///{LOCAL_DB_PATH}"
}
app.config['SQLALCHEMY_DATABASE_URI'] = SERVER_DB_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Exemple de modèles (si tu as déjà User et Cheque définis plus bas)
class UserServer(db.Model):
    __bind_key__ = 'server'
    __tablename__ = 'user_server'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    mac_address = db.Column(db.String(100))
    password = db.Column(db.String(200))


class UserLocal(db.Model):
    __bind_key__ = 'local'
    __tablename__ = 'user_local'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    mac_address = db.Column(db.String(100))
    password = db.Column(db.String(200))

# --- API : inscription ---
@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.json
    email = data.get("email")
    mac_address = data.get("mac_address")
    password = data.get("password")

    if not email or not mac_address or not password:
        return jsonify({"error": "Champs manquants"}), 400

    hashed_password = generate_password_hash(password)

    # ✅ Créer automatiquement la table locale si elle n’existe pas
    try:
        engine_local = db.get_engine(app, bind="local")
        UserLocal.metadata.create_all(engine_local)
        print("📁 Table 'user_local' vérifiée/créée.")
    except Exception as e:
        print(f"⚠️ Erreur lors de la création de la table locale : {e}")

    # --- 1️⃣ Création du user local ---
    user_local = UserLocal(email=email, mac_address=mac_address, password=hashed_password)
    db.session.add(user_local)
    db.session.commit()
    print("✅ Utilisateur enregistré localement.")

    # --- 2️⃣ Tentative de création sur le serveur ---
    try:
        with app.app_context():
            engine_server = db.get_engine(app, bind="server")
            UserServer.metadata.create_all(engine_server)
            existing_server = db.session.query(UserServer).filter_by(email=email).first()
            if not existing_server:
                user_server = UserServer(
                    email=email,
                    mac_address=mac_address,
                    password=hashed_password
                )
                db.session.add(user_server)
                db.session.commit()
                print("✅ Compte créé sur le serveur distant.")
    except Exception as e:
        db.session.rollback()
        print(f"⚠️ Erreur de connexion au serveur : {e}")

    return jsonify({
        "message": "Compte créé (local + serveur si disponible)."
    }), 201



@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    mac_address = data.get("mac_address")

    if not email or not password or not mac_address:
        return jsonify({"message": "Champs manquants"}), 400

    user = UserLocal.query.filter_by(email=email).first()
    if not user:
        return jsonify({"message": "Utilisateur non trouvé localement"}), 404

    if not check_password_hash(user.password, password):
        return jsonify({"message": "Mot de passe incorrect"}), 401

    if user.mac_address != mac_address:
        return jsonify({"message": "MAC non autorisée"}), 403

    # === Mettre l'utilisateur dans la session Flask ===
    session.clear()
    session['user_id'] = user.id
    session['email'] = user.email

    return jsonify({
        "message": "Connexion locale réussie ✅",
        "user_id": user.id,
        "email": user.email
    }), 200

@app.route("/api/current_user", methods=["GET"])
def current_user():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "Non authentifié"}), 401

    user = UserLocal.query.get(user_id)
    if not user:
        # cleanup si user supprimé localement
        session.clear()
        return jsonify({"error": "Utilisateur introuvable"}), 404

    return jsonify({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "mac_address": user.mac_address
    }), 200


# --- API : déconnexion ---
@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Déconnexion réussie"}), 200



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

@app.route('/')
def home():
    return "Backend des chèques connecté à PostgreSQL Render !"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))