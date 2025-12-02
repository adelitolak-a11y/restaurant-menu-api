from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF
import json
import os
from groq import Groq
from typing import Dict, List
import requests
from dotenv import load_dotenv

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


def generate_backend_json(restaurant_name: str, qr_mode: str, odoo_config: Dict = None) -> Dict:
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
            "street": "",
            "zipCode": "",
            "city": "",
            "country": "France"
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
    """Génère le fichier articles.json à partir du menu"""
    
    articles = []
    current_id = 4000
    
    # Mapping des catégories vers les pos_categ_id
    category_mapping = {
        "entrees": {"id": 17, "name": "NOURRITURE / ENTREES", "tva": 42, "course": "3"},
        "plats": {"id": 18, "name": "NOURRITURE / PLATS", "tva": 42, "course": "5"},
        "desserts": {"id": 19, "name": "NOURRITURE / DESSERTS", "tva": 42, "course": "7"},
        "boissons_soft": {"id": 6, "name": "BOISSONS / SOFTS-EAUX", "tva": 42, "course": "1"},
        "boissons_alcoolisees": {"id": 4, "name": "BOISSONS / ALCOOLS", "tva": 41, "course": "1"}
    }
    
    for category, items in menu_data.items():
        if category not in category_mapping:
            continue
            
        cat_info = category_mapping[category]
        
        for idx, item in enumerate(items):
            article = {
                "id": current_id,
                "name": item["nom"],
                "display_name": item["nom"],
                "description": False,
                "description_sale": item.get("description", False),
                "list_price": item["prix"],
                "taxes_id": [cat_info["tva"]],
                "standard_price": 0,
                "pos_categ_id": [cat_info["id"], cat_info["name"]],
                "sale_area": [],
                "image_512": False,
                "is_pack": False,
                "menu_ids": [],
                "only_menu": False,
                "product_tag_ids": [],
                "product_rank": [1, "Apéritif 1"],
                "priority": "0",
                "sequence": idx,
                "extra_cost": [],
                "en_GB": {
                    "display_name": item["nom"],
                    "pos_categ_id": [cat_info["id"], cat_info["name"]],
                    "description_sale": item.get("description", False)
                }
            }
            
            articles.append(article)
            current_id += 1
    
    return articles


@app.get("/")
def home():
    return {
        "message": "🍽️ API Restaurant Menu Generator v3.0",
        "version": "3.0",
        "endpoints": {
            "/generate-menu": "POST - Génère 3 fichiers JSON (backend, frontend, articles)"
        }
    }


@app.post("/generate-menu")
async def generate_menu(
    restaurant_name: str = Form(...),
    color1: str = Form(...),
    color2: str = Form(...),
    color3: str = Form(...),
    qr_mode: str = Form("unique"),
    menu_file: UploadFile = File(None),
    manual_menu: str = Form(None)  # ← NOUVEAU : pour la saisie manuelle
):
    """Génère les 3 fichiers JSON nécessaires"""
    try:
        # 1. Obtenir les données du menu
        if manual_menu:
            # Mode saisie manuelle
            try:
                menu_data = json.loads(manual_menu)
                print(f"✅ Menu manuel reçu avec {sum(len(v) for v in menu_data.values())} articles")
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"JSON manuel invalide: {str(e)}")
        
        elif menu_file:
            # Mode PDF
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
        
        # 2. Générer les 3 fichiers JSON
        colors = [color1, color2, color3]
        
        backend_json = generate_backend_json(restaurant_name, qr_mode)
        frontend_json = generate_frontend_json(restaurant_name, colors)
        articles_json = generate_articles_json(menu_data, backend_json["restaurantId"])
        
        # 3. Retourner les 3 fichiers
        return {
            "success": True,
            "restaurant_id": backend_json["restaurantId"],
            "files": {
                "backend": json.dumps(backend_json, indent=2, ensure_ascii=False),
                "frontend": json.dumps(frontend_json, indent=2, ensure_ascii=False),
                "articles": json.dumps(articles_json, indent=2, ensure_ascii=False)
            },
            "stats": {
                "total_articles": len(articles_json),
                "entrees": len(menu_data.get("entrees", [])),
                "plats": len(menu_data.get("plats", [])),
                "desserts": len(menu_data.get("desserts", [])),
                "boissons_soft": len(menu_data.get("boissons_soft", [])),
                "boissons_alcoolisees": len(menu_data.get("boissons_alcoolisees", []))
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
