from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF
import json
import os
from groq import Groq
from typing import Dict, List
import requests
from dotenv import load_dotenv
import paramiko

load_dotenv()

app = FastAPI(title="Restaurant Menu Generator API", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("⚠️  GROQ_API_KEY non définie dans .env")

groq_client = Groq(api_key=GROQ_API_KEY)

# Configuration Odoo
ODOO_URL = os.getenv("ODOO_URL", "https://ton-instance.odoo.com")
ODOO_DB = os.getenv("ODOO_DB", "nom_base")
ODOO_USERNAME = os.getenv("ODOO_USERNAME", "admin")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "")

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extrait le texte d'un PDF avec PyMuPDF"""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lecture PDF: {str(e)}")

def classify_menu_with_groq(text: str) -> Dict:
    """Utilise Groq pour classifier le menu complet"""
    
    prompt = f"""Tu es un expert en restauration. Analyse ce texte de menu et extrait TOUS les plats avec leurs prix.

TEXTE DU MENU:
{text}

Réponds UNIQUEMENT avec un JSON dans ce format (sans texte avant ou après):
{{
  "entrees": [
    {{"nom": "Soupe à l'oignon", "prix": 8.50, "description": "..."}}
  ],
  "plats": [
    {{"nom": "Steak frites", "prix": 22.00, "description": "..."}}
  ],
  "desserts": [
    {{"nom": "Tarte tatin", "prix": 7.50, "description": "..."}}
  ],
  "boissons_soft": [
    {{"nom": "Coca-Cola", "prix": 4.50}}
  ],
  "boissons_alcoolisees": [
    {{"nom": "Vin rouge (verre)", "prix": 6.00}}
  ],
  "cocktails": [
    {{"nom": "Mojito", "prix": 12.00, "description": "..."}}
  ],
  "mocktails": [
    {{"nom": "Virgin Mojito", "prix": 8.00, "description": "..."}}
  ],
  "bieres": [
    {{"nom": "1664 - 25cl", "prix": 6.00}}
  ],
  "vins_blancs": [
    {{"nom": "Chablis (verre)", "prix": 8.00}}
  ],
  "vins_rouges": [
    {{"nom": "Bordeaux (verre)", "prix": 7.50}}
  ],
  "vins_roses": [
    {{"nom": "Provence (verre)", "prix": 7.00}}
  ],
  "champagnes": [
    {{"nom": "Champagne Brut (coupe)", "prix": 15.00}}
  ],
  "cafeterie": [
    {{"nom": "Expresso", "prix": 3.50}}
  ]
}}

RÈGLES:
- N'utilise JAMAIS de guillemets dans les noms de plats (remplace " par ')
- Extrais TOUS les plats et boissons avec leurs prix
- Si un prix a une virgule (12,50), convertis en point (12.50)
- Retourne UNIQUEMENT le JSON, rien d'autre"""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=10000
        )
        
        response_text = response.choices[0].message.content.strip()
        
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]
        
        menu_json = json.loads(response_text)
        return menu_json
        
    except json.JSONDecodeError as e:
        print(f"⚠️  JSON invalide reçu de Groq")
        raise HTTPException(status_code=500, detail=f"Erreur parsing JSON: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur Groq API: {str(e)}")

def generate_backend_json(restaurant_name: str, qr_mode: str, address: Dict, odoo_config: Dict = None) -> Dict:
    """Génère le fichier backend.json"""
    
    backend = {
        "type": "Odoo",
        "odooUrl": odoo_config.get("url", ODOO_URL) if odoo_config else ODOO_URL,
        "odooDb": odoo_config.get("db", ODOO_DB) if odoo_config else ODOO_DB,
        "odooLogin": odoo_config.get("login", ODOO_USERNAME) if odoo_config else ODOO_USERNAME,
        "odooPwd": odoo_config.get("password", ODOO_PASSWORD) if odoo_config else ODOO_PASSWORD,
        "provenanceContact": "Pleazze",
        "defaultWaiterId": 2,
        "odooCompanyId": "",
        "odooTipId": 3134,
        "sms": {
            "type": "SMSLinker",
            "ident": {
                "subject": f"{restaurant_name}",
                "content": "Votre code d'identification : $CODE$"
            }
        },
        "payment": {
            "paymentId": "4",
            "stripe_secret_key": "sk_test_...",
            "lyfUrl": "https://sandbox-webpos.lyf.eu/fr/plugin/PaymentCb.aspx",
            "lyfPosId": "",
            "lyfPosKey": ""
        },
        "address": {
            "street": address.get("street", ""),
            "zipCode": address.get("zip_code", ""),
            "city": address.get("city", ""),
            "country": address.get("country", "France")
        },
        "menu": {
            "menus": [],
            "sections": [],
            "drinks": [],
            "courses": {
                "choicesForCourse": {},
                "courseByGroup": {},
                "courseLabels": {
                    "3": {"fr": "Entrée", "en": "Starter", "class": "overt-courseId", "courseId": "3"},
                    "5": {"fr": "Plat", "en": "Main", "class": "obleucl-courseId", "courseId": "5"},
                    "7": {"fr": "Dessert", "en": "Dessert", "class": "oorange-courseId", "courseId": "7"}
                },
                "courseOrder": ["3", "5", "7"]
            }
        },
        "restaurantName": restaurant_name,
        "restaurantId": restaurant_name.lower().replace(" ", "_"),
        "supervisorRole": "manager",
        "qrMode": qr_mode
    }
    
    return backend

def generate_frontend_json(restaurant_name: str, colors: List[str]) -> Dict:
    """Génère le fichier frontend.json"""
    
    frontend = {
        "home": {
            "banners": [{
                "src": "/assets/img/banners/banner.png",
                "title": {
                    "fr": f"Bienvenue chez {restaurant_name}",
                    "en": f"Welcome to {restaurant_name}"
                }
            }],
            "blocs": [{
                "type": "text",
                "text": {
                    "fr": f"Découvrez notre carte et commandez directement depuis votre table via QR code.",
                    "en": f"Discover our menu and order directly from your table via QR code."
                },
                "classes": "none"
            }]
        },
        "menu": {
            "banner": {
                "src": "/assets/img/formule-background.png"
            }
        },
        "styles": {
            "colors": {
                "primary": colors[0],
                "accent": colors[1],
                "footer": colors[2]
            }
        },
        "payment": {
            "stripe_public_key": "pk_test_..."
        },
        "discountPercent": 0.05
    }
    
    return frontend

def generate_articles_json(menu_data: Dict, restaurant_id: str) -> List[Dict]:
    """Génère le fichier articles.json - EXACTEMENT comme l'exemple fourni"""
    
    articles = []
    current_id = 4000
    
    # Mapping EXACT basé sur votre fichier article.json
    category_mapping = {
        "entrees": {
            "id": 17,
            "name": "NOURRITURE / ENTREES",
            "tva": 42,
            "course": "3"
        },
        "plats": {
            "id": 18,
            "name": "NOURRITURE / SNACKING",  # Comme dans votre exemple
            "tva": 42,
            "course": "5"
        },
        "desserts": {
            "id": 19,
            "name": "NOURRITURE / DESSERTS",
            "tva": 42,
            "course": "7"
        },
        "boissons_soft": {
            "id": 6,
            "name": "BOISSONS / SOFTS-EAUX",  # EXACT comme votre exemple
            "tva": 42,
            "course": "1"
        },
        "boissons_alcoolisees": {
            "id": 13,  # Dans votre exemple c'est ALCOOLS = 13
            "name": "BOISSONS / ALCOOLS",
            "tva": 41,
            "course": "1"
        },
        "aperitifs": {
            "id": 4,
            "name": "BOISSONS / APERITIFS",
            "tva": 41,
            "course": "1"
        },
        "cocktails": {
            "id": 2,
            "name": "BOISSONS / COCKTAILS",
            "tva": 41,
            "course": "1"
        },
        "mocktails": {
            "id": 3,
            "name": "BOISSONS / MOCKTAILS",
            "tva": 42,
            "course": "1"
        },
        "bieres": {
            "id": 5,
            "name": "BOISSONS / BIERES",
            "tva": 41,
            "course": "1"
        },
        "vins_blancs": {
            "id": 8,
            "name": "BOISSONS / VINS VERRE BLANCS",
            "tva": 41,
            "course": "1"
        },
        "vins_rouges": {
            "id": 9,
            "name": "BOISSONS / VINS VERRE ROUGES",
            "tva": 41,
            "course": "1"
        },
        "vins_roses": {
            "id": 10,
            "name": "BOISSONS / VINS VERRE ROSES",
            "tva": 41,
            "course": "1"
        },
        "champagnes": {
            "id": 11,
            "name": "BOISSONS / CHAMPAGNES BLANCS",
            "tva": 41,
            "course": "1"
        },
        "champagnes_roses": {
            "id": 12,
            "name": "BOISSONS / CHAMPAGNES ROSÉ",
            "tva": 41,
            "course": "1"
        },
        "cafeterie": {
            "id": 7,
            "name": "BOISSONS / CAFETERIE",
            "tva": 42,
            "course": "1"
        },
        "bt_vins_blancs": {
            "id": 14,
            "name": "BOISSONS / BT VINS BLANCS",
            "tva": 41,
            "course": "1"
        },
        "bt_vins_rouges": {
            "id": 16,
            "name": "BOISSONS / BT VINS ROUGES",
            "tva": 41,
            "course": "1"
        },
        "bt_vins_roses": {
            "id": 15,
            "name": "BOISSONS / BT VINS ROSES",
            "tva": 41,
            "course": "1"
        }
    }
    
    for category, items in menu_data.items():
        if category not in category_mapping:
            print(f"⚠️  Catégorie '{category}' non mappée, ignorée")
            continue
            
        cat_info = category_mapping[category]
        
        for idx, item in enumerate(items):
            # Validation des données
            if "nom" not in item or "prix" not in item:
                print(f"⚠️  Article incomplet ignoré: {item}")
                continue
            
            # Conversion du prix en nombre (float ou int selon le cas)
            prix = float(item["prix"]) if isinstance(item["prix"], str) else item["prix"]
            
            # Structure EXACTE comme votre exemple
            article = {
                "id": current_id,
                "name": item["nom"],
                "display_name": item["nom"],
                "description": False,  # boolean false (pas string)
                "description_sale": item.get("description", False),  # False ou string
                "list_price": prix,  # nombre
                "taxes_id": [cat_info["tva"]],  # array avec 1 élément
                "standard_price": 0,  # nombre
                "pos_categ_id": [cat_info["id"], cat_info["name"]],  # [int, string]
                "sale_area": [],  # array vide
                "image_512": False,  # boolean
                "is_pack": False,  # boolean
                "menu_ids": [],  # array vide
                "only_menu": False,  # boolean
                "product_tag_ids": [],  # array vide
                "product_rank": [1, "Apéritif 1"],  # [int, string] EXACT
                "priority": "0",  # STRING "0"
                "sequence": idx,  # nombre qui s'incrémente
                "extra_cost": [],  # array vide
                "en_GB": {
                    "display_name": item["nom"],
                    "pos_categ_id": [cat_info["id"], cat_info["name"]],
                    "description_sale": item.get("description", False)
                }
            }
            
            articles.append(article)
            current_id += 1
    
    print(f"✅ {len(articles)} articles générés avec IDs de {4000} à {current_id-1}")
    return articles

@app.get("/")
def home():
    return {
        "message": "🍽️ API Restaurant Menu Generator v3.0",
        "version": "3.0",
        "endpoints": {
            "/extract-menu": "POST - Extrait le menu pour prévisualisation",
            "/generate-menu": "POST - Génère les 3 fichiers JSON finaux (backend, frontend, articles)"
        }
    }

@app.post("/extract-menu")
async def extract_menu(
    restaurant_name: str = Form(...),
    color1: str = Form(...),
    color2: str = Form(...),
    color3: str = Form(...),
    qr_mode: str = Form("unique"),
    street: str = Form(""),
    zip_code: str = Form(""),
    city: str = Form(""),
    country: str = Form("France"),
    menu_file: UploadFile = File(None),
    manual_menu: str = Form(None)
):
    """Extrait le menu pour prévisualisation (sans générer les JSON finaux)"""
    try:
        # 1. Obtenir les données du menu
        if manual_menu:
            try:
                menu_data = json.loads(manual_menu)
                print(f"✅ Menu manuel reçu avec {sum(len(v) for v in menu_data.values())} articles")
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"JSON manuel invalide: {str(e)}")
        
        elif menu_file:
            if not menu_file.filename.lower().endswith('.pdf'):
                raise HTTPException(status_code=400, detail="Le fichier doit être un PDF")
            
            pdf_content = await menu_file.read()
            text = extract_text_from_pdf(pdf_content)
            
            if not text.strip():
                raise HTTPException(status_code=400, detail="Impossible d'extraire du texte du PDF")
            
            menu_data = classify_menu_with_groq(text)
            print(f"✅ Menu extrait du PDF avec {sum(len(v) for v in menu_data.values())} articles")
        
        else:
            raise HTTPException(status_code=400, detail="Vous devez fournir soit un PDF soit un menu manuel")
        
        # Retourner uniquement les données extraites pour prévisualisation
        return {
            "success": True,
            "data": {
                "restaurant_name": restaurant_name,
                "qr_mode": qr_mode,
                "colors": {
                    "color1": color1,
                    "color2": color2,
                    "color3": color3
                },
                "address": {
                    "street": street,
                    "zip_code": zip_code,
                    "city": city,
                    "country": country
                },
                "menu": menu_data
            },
            "stats": {
                "total_articles": sum(len(v) for v in menu_data.values()),
                "par_categorie": {k: len(v) for k, v in menu_data.items()}
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

@app.post("/generate-menu")
async def generate_menu(
    restaurant_name: str = Form(...),
    color1: str = Form(...),
    color2: str = Form(...),
    color3: str = Form(...),
    qr_mode: str = Form("unique"),
    street: str = Form(""),
    zip_code: str = Form(""),
    city: str = Form(""),
    country: str = Form("France"),
    menu_file: UploadFile = File(None),
    manual_menu: str = Form(None),
    validated_menu: str = Form(None)
):
    """Génère les 3 fichiers JSON nécessaires"""
    try:
        # 1. Obtenir les données du menu
        if validated_menu:
            try:
                menu_data = json.loads(validated_menu)
                print(f"✅ Menu validé reçu avec {sum(len(v) for v in menu_data.values())} articles")
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"JSON validé invalide: {str(e)}")
        
        elif manual_menu:
            try:
                menu_data = json.loads(manual_menu)
                print(f"✅ Menu manuel reçu avec {sum(len(v) for v in menu_data.values())} articles")
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"JSON manuel invalide: {str(e)}")
        
        elif menu_file:
            if not menu_file.filename.lower().endswith('.pdf'):
                raise HTTPException(status_code=400, detail="Le fichier doit être un PDF")
            
            pdf_content = await menu_file.read()
            text = extract_text_from_pdf(pdf_content)
            
            if not text.strip():
                raise HTTPException(status_code=400, detail="Impossible d'extraire du texte du PDF")
            
            menu_data = classify_menu_with_groq(text)
            print(f"✅ Menu extrait du PDF avec {sum(len(v) for v in menu_data.values())} articles")
        
        else:
            raise HTTPException(status_code=400, detail="Vous devez fournir soit un PDF, soit un menu manuel, soit un menu validé")
        
        # 2. Préparer l'adresse
        address = {
            "street": street,
            "zip_code": zip_code,
            "city": city,
            "country": country
        }
        
        # 3. Générer les 3 fichiers JSON
        colors = [color1, color2, color3]
        
        backend_json = generate_backend_json(restaurant_name, qr_mode, address)
        frontend_json = generate_frontend_json(restaurant_name, colors)
        articles_json = generate_articles_json(menu_data, backend_json["restaurantId"])
        
        # 4. Retourner les 3 fichiers
        return {
            "success": True,
            "restaurant_id": backend_json["restaurantId"],
            "address": address,
            "files": {
                "backend": json.dumps(backend_json, indent=2, ensure_ascii=False),
                "frontend": json.dumps(frontend_json, indent=2, ensure_ascii=False),
                "articles": json.dumps(articles_json, indent=2, ensure_ascii=False)
            },
            "stats": {
                "total_articles": len(articles_json),
                "par_categorie": {k: len(menu_data.get(k, [])) for k in menu_data.keys()}
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")

@app.get("/health")
def health_check():
    return {
        "status": "running",
        "groq": "✅ OK" if GROQ_API_KEY else "❌ Non configuré",
        "version": "3.0"
    }

@app.post("/upload-to-server")
async def upload_to_server(
    restaurant_id: str = Form(...),
    backend_json: str = Form(...),
    frontend_json: str = Form(...),
    ftp_password: str = Form(...)
):
    """Upload les fichiers JSON générés sur le serveur via SFTP"""
    try:
        import paramiko  # Test si paramiko est installé
        
        SFTP_HOST = "178.32.198.72"
        SFTP_PORT = 2266
        SFTP_USER = "snadmin"
        TARGET_PATH = "/var/www/pleazze/data/config/abdel"
        
        # Log pour debug
        print(f"🔍 Tentative de connexion SFTP à {SFTP_HOST}:{SFTP_PORT}")
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        print("🔐 Connexion SSH...")
        ssh.connect(
            hostname=SFTP_HOST,
            port=SFTP_PORT,
            username=SFTP_USER,
            password=ftp_password,
            look_for_keys=False,
            allow_agent=False,
            timeout=30  # Augmenter le timeout
        )
        print("✅ SSH connecté")
        
        print("📂 Ouverture SFTP...")
        sftp = ssh.open_sftp()
        print("✅ SFTP ouvert")
        
        print(f"📁 Navigation vers {TARGET_PATH}...")
        sftp.chdir(TARGET_PATH)
        print("✅ Dossier trouvé")
        
        print("📤 Upload backend.json...")
        with sftp.file('backend.json', 'w') as f:
            f.write(backend_json)
        print("✅ backend.json uploadé")
        
        print("📤 Upload frontend.json...")
        with sftp.file('frontend.json', 'w') as f:
            f.write(frontend_json)
        print("✅ frontend.json uploadé")
        
        sftp.close()
        ssh.close()
        
        return {
            "success": True,
            "message": "Fichiers uploadés avec succès sur le serveur"
        }
        
    except ImportError:
        return {
            "success": False,
            "message": "❌ Paramiko n'est pas installé sur le serveur"
        }
    except paramiko.AuthenticationException:
        return {
            "success": False,
            "message": "❌ Mot de passe incorrect"
        }
    except TimeoutError:
        return {
            "success": False,
            "message": "❌ Timeout: le serveur Render ne peut pas atteindre ton serveur SFTP (firewall?)"
        }
    except paramiko.SSHException as e:
        return {
            "success": False,
            "message": f"❌ Erreur SSH: {str(e)}"
        }
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"❌ Erreur complète: {error_details}")
        return {
            "success": False,
            "message": f"❌ Erreur: {str(e)}"
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
