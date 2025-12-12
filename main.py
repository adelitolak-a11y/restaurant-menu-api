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
from PIL import Image
import io

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

def generate_backend_json(restaurant_name: str, qr_mode: str, address: Dict, odoo_config: Dict = None, version: int = 1) -> Dict:
    """Génère le fichier backend.json (version 1 ou 2)"""
    
    if version == 1:
        # Version complète (actuelle)
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
            "address": address,
            "menu": {
                "menus": [],
                "sections": [17, 18],
                "drinks": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
                "courses": {
                    "choicesForCourse": {},
                    "courseByGroup": {},
                    "courseLabels": {
                        "1": {"fr": "Apéro", "en": "Apetizer", "class": "brown-courseId", "courseId": "1"},
                        "2": {"fr": "Entrée", "en": "Starter", "class": "green-courseId", "courseId": "2"},
                        "3": {"fr": "Plat", "en": "Main", "class": "blue-courseId", "courseId": "3"},
                        "4": {"fr": "Dessert", "en": "Dessert", "class": "yellow-courseId", "courseId": "4"}
                    },
                    "courseOrder": ["1", "2", "3", "4"]
                }
            },
            "restaurantName": restaurant_name,
            "restaurantId": restaurant_name.lower().replace(" ", "_"),
            "supervisorRole": "manager",
            "qrMode": qr_mode
        }
    else:
        # Version 2 : seulement la section "menu"
        backend = {
            "menu": {
                "menus": [],
                "sections": [17, 18],
                "drinks": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
                "courses": {
                    "choicesForCourse": {},
                    "courseByGroup": {
                        "5000000479": 20000066039
                    },
                    "courseLabels": {
                        "1": {"fr": "Apéro", "en": "Apetizer", "class": "brown-courseId", "courseId": "1"},
                        "2": {"fr": "Entrée", "en": "Starter", "class": "green-courseId", "courseId": "2"},
                        "3": {"fr": "Plat", "en": "Main", "class": "blue-courseId", "courseId": "3"},
                        "4": {"fr": "Dessert", "en": "Dessert", "class": "yellow-courseId", "courseId": "4"}
                    },
                    "courseOrder": ["1", "2", "3", "4"]
                }
            }
        }
    
    return backend

def generate_frontend_json(restaurant_name: str, colors: Dict, version: int = 1) -> Dict:
    """Génère le fichier frontend.json (version 1 ou 2)"""
    
    if version == 1:
        return {
            "home": {
                "banners": [{
                    "src": "/var/www/pleazze/data/config/abdel/old/home-banner-pleazze-box.png",
                    "title": {
                        "fr": f"Bienvenue chez {restaurant_name}",
                        "en": f"Welcome to {restaurant_name}"
                    }
                }],
                "blocs": []
            },
            "menu": {
                "banner": {
                    "src": "/var/www/pleazze/data/config/abdel/old/menu-banner-pleazze-box.png"
                }
            },
            "styles": {
                "colors": {
                    "primary": colors.get("primary"),
                    "accent": colors.get("accent"),
                    "footer": colors.get("footer")
                }
            }
        }
    else:
        # VERSION 2 : Format complet avec les bons chemins
        return {
            "homeType": "home2",
            "clientMenuType": "clientMenu2",
            "cartType": "cart",
            "payType": "lyf-prepay",
            "menuType": "menu2",
            "drinkMenuType": "drinkMenu2",
            "identificationType": "ident2",
            "isIdentificationMandatory": False,
            "routeAfterIdentification": "pay/thankyou",
            "foodButtonEnabled": True,
            "happyHour": {
                "weekDays": [],
                "start": 24,
                "end": 24
            },
            "home": {
                "banners": [{
                    "src": "/var/www/pleazze/data/config/abdel/old/home-banner-pleazze-box.png",  # ✅ Chemin réel
                    "title": {
                        "fr": f"<b>SÉLECTIONNEZ</b>, <b>COMMANDEZ</b>, <b>PAYEZ</b> directement depuis votre smartphone.\n\nBienvenue chez {restaurant_name}",
                        "en": f"Choose, Order and Pay directly with your smartphone.\n\nWelcome to {restaurant_name}"
                    }
                }],
                "blocs": []
            },
            "menu": {
                "banner": {
                    "src": "/var/www/pleazze/data/config/abdel/old/menu-banner-pleazze-box.png"  # ✅ Chemin réel
                }
            },
            "styles": {
                "colors": {
                    "primary": colors.get("primary"),
                    "accent": colors.get("accent"),
                    "footer": colors.get("footer"),
                    "footer_accent": colors.get("footer_accent"),
                    "footer_font": "#FFFFFF",
                    "order_page_background": "#E4DFD8",
                    "order_page_font": "#252525",
                    "pay_page_background": "#E4DFD8",
                    "pay_page_font": "#252525",
                    "form_input_background": "#F5F5F5",
                    "form_input_font": "#8A8A8A",
                    "button_accent_background": colors.get("button_accent_bg"),
                    "button_accent_font": "#E4DFD8",
                    "button_primary_background": "#E4DFD8",
                    "button_primary_font": colors.get("button_primary_font"),
                    "button_menu_block": "#FFFFFF",
                    "button_menu_block_font": colors.get("button_menu_block_font")
                }
            }
        }

def generate_menus_json(menu_data: Dict, restaurant_id: str) -> Dict:
    """Génère le fichier menus.4.json au format Odoo"""
    
    menus_json = {
        "menus": [],
        "sections": [
            {
                "name": {"fr": "NOURRITURE", "en": "FOOD"},
                "articles": []
            }
        ],
        "drinks": []
    }
    
    # Mapping des catégories
    category_mapping = {
        "entrees": {"section": "sections", "name": {"fr": "ENTRÉES", "en": "STARTERS"}},
        "plats": {"section": "sections", "name": {"fr": "PLATS", "en": "MAINS"}},
        "desserts": {"section": "sections", "name": {"fr": "DESSERTS", "en": "DESSERTS"}},
        "boissons_soft": {"section": "drinks", "name": {"fr": "SOFTS-EAUX", "en": "SOFT DRINKS"}},
        "boissons_alcoolisees": {"section": "drinks", "name": {"fr": "ALCOOLS", "en": "SPIRITS"}},
        "cocktails": {"section": "drinks", "name": {"fr": "COCKTAILS", "en": "COCKTAILS"}},
        "mocktails": {"section": "drinks", "name": {"fr": "MOCKTAILS", "en": "MOCKTAILS"}},
        "bieres": {"section": "drinks", "name": {"fr": "BIÈRES", "en": "BEERS"}},
        # ... ajoute les autres catégories
    }
    
    current_id = 4000
    
    for category, items in menu_data.items():
        if category not in category_mapping:
            continue
            
        cat_info = category_mapping[category]
        section_type = cat_info["section"]
        
        # Créer une section pour cette catégorie
        category_section = {
            "name": cat_info["name"],
            "articles": []
        }
        
        for item in items:
            article = {
                "name": {"fr": item["nom"], "en": item["nom"]},
                "articleId": str(current_id),
                "posName": item["nom"],
                "price": {"priceId": "", "amount": float(item["prix"])},
                "img": "",
                "descr": {"fr": item.get("description", ""), "en": item.get("description", "")},
                "allergens": {"fr": "", "en": ""},
                "additional": {"fr": "", "en": ""},
                "wine_pairing": {"fr": "", "en": ""},
                "options": [],
                "defaultCourseId": 1,
                "choicesForCourse": []
            }
            
            category_section["articles"].append(article)
            current_id += 1
        
        # Ajouter la section au bon endroit
        if section_type == "sections":
            menus_json["sections"].append(category_section)
        else:
            menus_json["drinks"].append(category_section)
    
    return menus_json

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
    color_primary: str = Form("#db5543"),
    color_accent: str = Form("#db5543"),
    color_footer: str = Form("#db5543"),
    color_footer_accent: str = Form("#eb5c27"),
    color_button_accent_bg: str = Form("#db5543"),
    color_button_primary_font: str = Form("#db5543"),
    color_button_menu_block_font: str = Form("#eb5c27"),
    qr_mode: str = Form("unique"),
    street: str = Form(""),
    zip_code: str = Form(""),
    city: str = Form(""),
    country: str = Form("France"),
    home_banner: UploadFile = File(None),  # ✅ NOUVEAU
    menu_banner: UploadFile = File(None),  # ✅ NOUVEAU
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
                    "primary": color_primary,
                    "accent": color_accent,
                    "footer": color_footer,
                    "footer_accent": color_footer_accent,
                    "button_accent_background": color_button_accent_bg,
                    "button_primary_font": color_button_primary_font,
                    "button_menu_block_font": color_button_menu_block_font
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
    color_primary: str = Form("#db5543"),
    color_accent: str = Form("#db5543"),
    color_footer: str = Form("#db5543"),
    color_footer_accent: str = Form("#eb5c27"),
    color_button_accent_bg: str = Form("#db5543"),
    color_button_primary_font: str = Form("#db5543"),
    color_button_menu_block_font: str = Form("#eb5c27"),
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
        colors = {
            "primary": color_primary,
            "accent": color_accent,
            "footer": color_footer,
            "footer_accent": color_footer_accent,
            "button_accent_background": color_button_accent_bg,
            "button_primary_font": color_button_primary_font,
            "button_menu_block_font": color_button_menu_block_font
        }
        
    
        # ✅ NOUVEAU - Générer backend AVANT menus
        backend_json = generate_backend_json(restaurant_name, qr_mode, address, version=1)
        backend_2_json = generate_backend_json(restaurant_name, qr_mode, address, version=2)
        menus_json = generate_menus_json(menu_data, backend_json["restaurantId"])
        frontend_json = generate_frontend_json(restaurant_name, colors, version=1)
        frontend_2_json = generate_frontend_json(restaurant_name, colors, version=2)
        menus_2_json = menus_json.copy()
        
        # 4. Retourner les 3 fichiers
        return {
            "success": True,
            "restaurant_id": backend_json["restaurantId"],
            "address": address,
            "files": {
                "backend": json.dumps(backend_json, indent=2, ensure_ascii=False),
                "frontend": json.dumps(frontend_json, indent=2, ensure_ascii=False),
                "menus": json.dumps(menus_json, ensure_ascii=False, separators=(',', ':')),
                "backend_2": json.dumps(backend_2_json, indent=2, ensure_ascii=False),
                "frontend_2": json.dumps(frontend_2_json, indent=2, ensure_ascii=False),
                "menus_2": json.dumps(menus_2_json,  ensure_ascii=False, separators=(',', ':'))
            },
            "stats": {
                "total_articles": sum(len(v) for v in menu_data.values()),  # ✅ CORRECT
                "entrees": len(menu_data.get('entrees', [])),
                "plats": len(menu_data.get('plats', [])),
                "desserts": len(menu_data.get('desserts', [])),
                "boissons_soft": len(menu_data.get('boissons_soft', [])),
                "boissons_alcoolisees": len(menu_data.get('boissons_alcoolisees', []))
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

# Ajoute cet endpoint dans ton API pour tester

@app.post("/test-sftp-connection")
async def test_sftp_connection(ftp_password: str = Form(...)):
    """Endpoint de test pour diagnostiquer la connexion SFTP"""
    results = {
        "tests": [],
        "success": False
    }
    
    try:
        # Test 1: Paramiko installé ?
        results["tests"].append({"step": "Import paramiko", "status": "testing"})
        import paramiko
        results["tests"][-1]["status"] = "✅ OK"
        
        # Test 2: Connexion SSH
        results["tests"].append({"step": "Connexion SSH", "status": "testing"})
        SFTP_HOST = "178.32.198.72"
        SFTP_PORT = 2266
        SFTP_USER = "snadmin"
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        ssh.connect(
            hostname=SFTP_HOST,
            port=SFTP_PORT,
            username=SFTP_USER,
            password=ftp_password,
            look_for_keys=False,
            allow_agent=False,
            timeout=30
        )
        results["tests"][-1]["status"] = "✅ OK"
        
        # Test 3: Ouverture SFTP
        results["tests"].append({"step": "Ouverture session SFTP", "status": "testing"})
        sftp = ssh.open_sftp()
        results["tests"][-1]["status"] = "✅ OK"
        
        # Test 4: Navigation vers le dossier
        results["tests"].append({"step": "Navigation vers dossier", "status": "testing"})
        TARGET_PATH = "/var/www/pleazze/data/config/abdel"
        sftp.chdir(TARGET_PATH)
        results["tests"][-1]["status"] = "✅ OK"
        results["tests"][-1]["details"] = f"Dossier: {sftp.getcwd()}"
        
        # Test 5: Liste des fichiers
        results["tests"].append({"step": "Liste des fichiers", "status": "testing"})
        files = sftp.listdir()
        results["tests"][-1]["status"] = "✅ OK"
        results["tests"][-1]["details"] = f"{len(files)} fichiers trouvés"
        
        # Test 6: Test d'écriture
        results["tests"].append({"step": "Test d'écriture", "status": "testing"})
        test_content = "Test de connexion SFTP depuis Render"
        with sftp.file('test_connection.txt', 'w') as f:
            f.write(test_content)
        results["tests"][-1]["status"] = "✅ OK"
        
        sftp.close()
        ssh.close()
        
        results["success"] = True
        results["message"] = "✅ Tous les tests sont passés ! La connexion SFTP fonctionne."
        
    except ImportError as e:
        results["tests"].append({
            "step": "Import paramiko",
            "status": "❌ ERREUR",
            "error": f"Paramiko n'est pas installé: {str(e)}"
        })
        results["message"] = "❌ Paramiko n'est pas installé dans requirements.txt"
        
    except paramiko.AuthenticationException:
        if results["tests"]:
            results["tests"][-1]["status"] = "❌ ERREUR"
            results["tests"][-1]["error"] = "Mot de passe incorrect"
        results["message"] = "❌ Authentification échouée - Mot de passe incorrect"
        
    except Exception as e:
        if results["tests"]:
            results["tests"][-1]["status"] = "❌ ERREUR"
            results["tests"][-1]["error"] = str(e)
            results["tests"][-1]["type"] = type(e).__name__
        results["message"] = f"❌ Erreur: {type(e).__name__}: {str(e)}"
    
    return results

@app.get("/test-network")
async def test_network():
    import socket
    try:
        # Test si Render peut atteindre ton serveur
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex(("178.32.198.72", 2266))
        sock.close()
        
        if result == 0:
            return {"status": "✅ Port 2266 accessible depuis Render"}
        else:
            return {"status": f"❌ Port 2266 non accessible (code: {result})"}
    except Exception as e:
        return {"status": f"❌ Erreur: {str(e)}"}

@app.post("/upload-to-server")
async def upload_to_server(
    restaurant_id: str = Form(...),
    backend_json: str = Form(...),
    backend_2_json: str = Form(...),  # ← AJOUTER
    frontend_json: str = Form(...),
    frontend_2_json: str = Form(...),  # ← AJOUTER
    menus_json: str = Form(...),
    menus_2_json: str = Form(...),  # ← AJOUTER
    ftp_password: str = Form(...),
    home_banner: UploadFile = File(None),
    menu_banner: UploadFile = File(None)
):
    """Upload les fichiers JSON + images sur le serveur via SFTP"""
    
    def convert_to_png(image_file):
        """Convertit n'importe quelle image en PNG"""
        image_bytes = image_file.read()
        image = Image.open(io.BytesIO(image_bytes))
        
        # Convertir en PNG
        png_buffer = io.BytesIO()
        image.save(png_buffer, format='PNG')
        png_buffer.seek(0)
        return png_buffer.getvalue()
    
    try:
        import paramiko
        
        SFTP_HOST = "178.32.198.72"
        SFTP_USER = "snadmin"
        
        # Connexion unique sur port 2266
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=SFTP_HOST, 
            port=2266,
            username=SFTP_USER, 
            password=ftp_password, 
            timeout=30,
            look_for_keys=False,
            allow_agent=False
        )
        
        sftp = ssh.open_sftp()
        
        CONFIG_PATH = f"/var/www/pleazze/data/config/abdel"
        CACHE_PATH = f"/var/www/pleazze/data/cache/abdel/data_2025-07-29_17-25-11"
        IMAGES_PATH = f"/var/www/pleazze/data/config/abdel/old"
        
        # Créer les dossiers
        for path in [CONFIG_PATH, CACHE_PATH, IMAGES_PATH]:
            try:
                parts = path.split('/')
                current = ''
                for part in parts:
                    if not part:
                        continue
                    current += '/' + part
                    try:
                        sftp.mkdir(current)
                    except:
                        pass
            except:
                pass
        
        # Upload JSON dans /config/
        with sftp.file(f'{CONFIG_PATH}/backend.json', 'w') as f:
            f.write(backend_json)

        with sftp.file(f'{CONFIG_PATH}/backend_2.json', 'w') as f:
            f.write(backend_2_json)  # ← Utiliser backend_2_json au lieu de backend_json

        with sftp.file(f'{CONFIG_PATH}/frontend.json', 'w') as f:
            f.write(frontend_json)

        with sftp.file(f'{CONFIG_PATH}/frontend_2.json', 'w') as f:
            f.write(frontend_2_json)  # ← Utiliser frontend_2_json au lieu de frontend_json

        # Upload JSON dans /cache/
        with sftp.file(f'{CACHE_PATH}/menus.4.json', 'w') as f:
            f.write(menus_json)

        with sftp.file(f'{CACHE_PATH}/menus_2.4.json', 'w') as f:
            f.write(menus_2_json)  # ← Utiliser menus_2_json au lieu de menus_json
        
        # Upload des images (converties en PNG)
        uploaded_images = []
        
        if home_banner:
            png_content = convert_to_png(home_banner.file)
            with sftp.file(f'{IMAGES_PATH}/home-banner-pleazze-box.png', 'wb') as f:
                f.write(png_content)
            uploaded_images.append("home-banner-pleazze-box.png")
        
        if menu_banner:
            png_content = convert_to_png(menu_banner.file)
            with sftp.file(f'{IMAGES_PATH}/menu-banner-pleazze-box.png', 'wb') as f:
                f.write(png_content)
            uploaded_images.append("menu-banner-pleazze-box.png")
        
        sftp.close()
        ssh.close()
        
        return {
            "success": True, 
            "message": f"✅ {6 + len(uploaded_images)} fichiers uploadés avec succès",
            "details": {
                "config": ["backend.json", "backend_2.json", "frontend.json", "frontend_2.json"],
                "cache": ["menus.4.json", "menus_2.4.json"],
                "images": uploaded_images if uploaded_images else ["Aucune image uploadée"]
            }
        }
    except Exception as e:
        return {"success": False, "message": f"Erreur SFTP: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
