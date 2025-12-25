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
    
    prompt = f"""Tu es un expert en extraction de menus de restaurants. Tu dois analyser cette carte et extraire TOUS les articles avec une précision maximale.

TEXTE DE LA CARTE :
{text}

CATÉGORIES DISPONIBLES :

**NOURRITURE :**
- entrees : entrées/starters (peut inclure les salades SI la carte ne les sépare pas)
- salades : toutes les salades (Niçoise, Caesar, etc.) - UNIQUEMENT si la carte a une section "SALADES" dédiée
- plats : plats principaux/mains
- desserts : desserts
- planches : planches à partager (charcuterie, fromage, mixte)
- tapas : tapas, petits plaisirs croustillants, snacking, amuse-bouches
- pinsa_pizza : pinsa, pizza
- pates : pâtes, pasta
- burgers : tous les burgers
- brasserie : plats de brasserie (fish & chips, moules frites, tartares, bavettes, cuisse de canard, etc.)
- accompagnements : frites, salade verte, bol de frites, garnitures, riz, purées, légumes grillés, pommes grenailles, etc.

**BOISSONS NON-ALCOOLISÉES :**
- boissons_soft : Coca, Perrier, Orangina, etc.
- jus : jus de fruits, pressés
- boissons_chaudes : café, thé, chocolat chaud

**BOISSONS ALCOOLISÉES - BIÈRES :**
- bieres_pression : bières pression (25cl, 50cl)
- bieres_bouteilles : bières en bouteilles

**BOISSONS ALCOOLISÉES - VINS :**
- vins_blancs_verre : vins blancs au verre
- vins_rouges_verre : vins rouges au verre
- vins_roses_verre : vins rosés au verre
- vins_blancs_bouteille : vins blancs en bouteille (75cl)
- vins_rouges_bouteille : vins rouges en bouteille (75cl)
- vins_roses_bouteille : vins rosés en bouteille (75cl)
- vins_blancs_magnum : vins blancs magnum/jeroboam/mathusalem (150cl, 300cl, 600cl)
- vins_rouges_magnum : vins rouges magnum/jeroboam/mathusalem (150cl, 300cl, 600cl)
- vins_roses_magnum : vins rosés magnum/jeroboam/mathusalem (150cl, 300cl, 600cl)

**BOISSONS ALCOOLISÉES - CHAMPAGNES :**
- champagnes_coupe : champagnes au verre/coupe
- champagnes_bouteille : champagnes en bouteille
- champagnes_magnum : champagnes magnum et plus

**BOISSONS ALCOOLISÉES - APÉRITIFS :**
- aperitifs : Ricard, Pastis, Porto, Martini, Campari, Kir, etc.
- spritz : tous les spritz

**BOISSONS ALCOOLISÉES - COCKTAILS :**
- cocktails : cocktails avec alcool
- mocktails : cocktails sans alcool

**BOISSONS ALCOOLISÉES - SPIRITUEUX :**
- rhums : tous les rhums (format verre/bouteille/magnum dans le nom si applicable)
- vodkas : toutes les vodkas (format verre/bouteille/magnum dans le nom si applicable)
- gins : tous les gins (format verre/bouteille/magnum dans le nom si applicable)
- tequilas : toutes les tequilas (format verre/bouteille/magnum dans le nom si applicable)
- whiskies : tous les whiskies/whisky (format verre/bouteille/magnum dans le nom si applicable)
- digestifs : liqueurs, digestifs divers, Limoncello, Get 27, etc.
- cognacs_armagnacs : cognacs, armagnacs

**RÈGLES DE CLASSIFICATION CRITIQUES :**
1. **RESPECTE L'ORGANISATION DE LA CARTE** : Si la carte met les salades dans "NOS ENTRÉES", alors mets-les dans "entrees". Ne crée "salades" QUE si la carte a une section "NOS SALADES" distincte.
2. **ACCOMPAGNEMENTS** : Frites, bol de frites, salade verte, purées, riz, légumes, pommes grenailles = catégorie "accompagnements"
3. **BOISSONS_SOFT** : UNIQUEMENT Coca, Sprite, Perrier, sodas, sirops, jus industriels (PAS les accompagnements)
4. **ANALYSE LA STRUCTURE** : Regarde les titres de sections dans la carte (ex: "NOS ENTRÉES", "LA BRASSERIE", "NOS SALADES") pour déterminer où classer chaque article

**IMPORTANT POUR LES TABLEAUX D'ALCOOLS :**
Si tu vois un tableau comme :          Verre    Bouteille   Magnum
JACK DANIEL'S  10€      130€        -
GREY GOOSE     12.50€   150€       290€
Crée 3 articles :
- "JACK DANIEL'S Verre" (10€) dans whiskies
- "JACK DANIEL'S Bouteille" (130€) dans whiskies
- "GREY GOOSE Verre" (12.50€) dans vodkas
- "GREY GOOSE Bouteille" (150€) dans vodkas
- "GREY GOOSE Magnum" (290€) dans vodkas
NE CRÉE PAS d'article pour les "-"

**RÈGLES STRICTES :
1. Extrais TOUS les articles même s'ils semblent incomplets
2. Si un prix contient une virgule (12,50), convertis-le en point (12.50)
3. N'utilise JAMAIS de guillemets doubles " dans les noms (remplace par ')
4. Pour les formats, note-les dans le nom : "Coca-Cola 33cl", "Bière pression 25cl"
5. Si plusieurs formats existent (25cl/50cl), crée un article par format
6. Pour les vins/champagnes, distingue verre/coupe/bouteille/magnum/jeroboam/mathusalem
7. **CRITIQUE : Si un article N'A PAS de description dans la carte, mets "description": false (PAS le nom du produit)**
8. **IMPORTANT : Si un alcool a plusieurs formats (verre/bouteille/magnum), crée UN ARTICLE PAR FORMAT avec le format dans le nom**
9. **CRITIQUE : Les ROSÉS ne sont PAS des BLANCS ! Classe-les correctement dans vins_roses_**
10. **CRITIQUE : Si un prix est marqué "-" ou absent, NE CRÉE PAS L'ARTICLE (ignore-le complètement)**
11. **TABLES/TABLEAUX : Si tu vois un tableau avec colonnes Verre/Bouteille/Magnum, extrais CHAQUE COLONNE comme un article séparé**
12. **BON SENS : Utilise ton intelligence pour classifier correctement selon le TYPE de plat, si tu constates une incohérence**
13. **CATEGORIES VIDES : Si une catégorie n'a AUCUN article, omets-la complètement du JSON**
14. **ACCOMPAGNEMENTS vs SOFTS** : Les frites, purées, riz, légumes vont dans "accompagnements", PAS dans "boissons_soft"

FORMAT DE RÉPONSE (JSON UNIQUEMENT, pas de texte avant/après) :
Retourne UNIQUEMENT les catégories qui contiennent au moins 1 article.
Si une catégorie est vide, ne l'inclus pas dans le JSON.

FORMAT DE RÉPONSE (JSON UNIQUEMENT, pas de texte avant/après) :
{{
  "entrees": [...],
  "salades": [...],
  "plats": [...],
  "desserts": [...],
  "planches": [...],
  "tapas": [...],
  "pinsa_pizza": [...],
  "pates": [...],
  "burgers": [...],
  "brasserie": [...],
  "accompagnements": [...],
  "boissons_soft": [...],  // TOUJOURS PRÉSENT (même vide)
  "jus": [...],
  "boissons_chaudes": [...],
  "bieres_pression": [...],
  "bieres_bouteilles": [...],
  "vins_blancs_verre": [...],
  "vins_rouges_verre": [...],
  "vins_roses_verre": [...],
  "vins_blancs_bouteille": [...],
  "vins_rouges_bouteille": [...],
  "vins_roses_bouteille": [...],
  "vins_blancs_magnum": [...],
  "vins_rouges_magnum": [...],
  "vins_roses_magnum": [...],
  "champagnes_coupe": [...],
  "champagnes_bouteille": [...],
  "champagnes_magnum": [...],
  "aperitifs": [...],
  "spritz": [...],
  "cocktails": [...],
  "mocktails": [...],
  "rhums": [...],
  "vodkas": [...],
  "gins": [...],
  "tequilas": [...],
  "whiskies": [...],
  "digestifs": [...],
  "cognacs_armagnacs": [...]
}}

Chaque article doit avoir ce format exact :
{{"nom": "...", "prix": 12.50, "description": "..." ou false}}

IMPORTANT : Retourne UNIQUEMENT le JSON, rien d'autre !"""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=16000
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
    

def clean_empty_categories(menu_data: Dict) -> Dict:
    """Supprime les catégories vides du menu"""
    cleaned = {}
    for k, v in menu_data.items():
        # Garde uniquement les catégories non vides
        if v and len(v) > 0:
            cleaned[k] = v
    return cleaned

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
    
    # ✅ NOUVEAU : Chemins selon les instructions de Youri
    safe_restaurant_name = restaurant_name.lower().replace(' ', '-').replace('/', '-')
    home_banner_path = f"/static/adel/home-banner-{safe_restaurant_name}.png"
    menu_banner_path = f"/static/adel/menu-banner-{safe_restaurant_name}.png"
    
    if version == 1:
        return {
            "home": {
                "banners": [{
                    "src": home_banner_path,
                    "title": {
                        "fr": f"Bienvenue chez {restaurant_name}",
                        "en": f"Welcome to {restaurant_name}"
                    }
                }],
                "blocs": []
            },
            "menu": {
                "banner": {
                    "src": menu_banner_path
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
        # VERSION 2
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
                    "src": home_banner_path,
                    "title": {
                        "fr": f"<b>SÉLECTIONNEZ</b>, <b>COMMANDEZ</b>, <b>PAYEZ</b> directement depuis votre smartphone.\n\nBienvenue chez {restaurant_name}",
                        "en": f"Choose, Order and Pay directly with your smartphone.\n\nWelcome to {restaurant_name}"
                    }
                }],
                "blocs": []
            },
            "menu": {
                "banner": {
                    "src": menu_banner_path
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
        "sections": [],
        "drinks": []
    }
    
    # Mapping des catégories
    category_mapping = {
        "entrees": {"section": "sections", "name": {"fr": "ENTRÉES", "en": "STARTERS"}},
        "salades": {"section": "sections", "name": {"fr": "SALADES", "en": "SALADS"}},
        "plats": {"section": "sections", "name": {"fr": "PLATS", "en": "MAINS"}},
        "desserts": {"section": "sections", "name": {"fr": "DESSERTS", "en": "DESSERTS"}},
        "planches": {"section": "sections", "name": {"fr": "PLANCHES", "en": "BOARDS"}},
        "tapas": {"section": "sections", "name": {"fr": "TAPAS", "en": "TAPAS"}},
        "pinsa_pizza": {"section": "sections", "name": {"fr": "PINSA & PIZZA", "en": "PINSA & PIZZA"}},
        "pates": {"section": "sections", "name": {"fr": "PÂTES", "en": "PASTA"}},
        "burgers": {"section": "sections", "name": {"fr": "BURGERS", "en": "BURGERS"}},
        "brasserie": {"section": "sections", "name": {"fr": "LA BRASSERIE", "en": "BRASSERIE"}},
        "accompagnements": {"section": "sections", "name": {"fr": "ACCOMPAGNEMENTS", "en": "SIDE DISHES"}},
        
        "boissons_soft": {"section": "drinks", "name": {"fr": "SOFTS-EAUX", "en": "SOFT DRINKS"}},
        "jus": {"section": "drinks", "name": {"fr": "JUS", "en": "JUICES"}},
        "boissons_chaudes": {"section": "drinks", "name": {"fr": "CAFÉTERIE", "en": "HOT DRINKS"}},
        
        "bieres_pression": {"section": "drinks", "name": {"fr": "BIÈRES PRESSION", "en": "DRAFT BEERS"}},
        "bieres_bouteilles": {"section": "drinks", "name": {"fr": "BIÈRES BOUTEILLES", "en": "BOTTLED BEERS"}},
        
        "vins_blancs_verre": {"section": "drinks", "name": {"fr": "VINS BLANCS VERRE", "en": "WHITE WINES GLASS"}},
        "vins_rouges_verre": {"section": "drinks", "name": {"fr": "VINS ROUGES VERRE", "en": "RED WINES GLASS"}},
        "vins_roses_verre": {"section": "drinks", "name": {"fr": "VINS ROSÉS VERRE", "en": "ROSÉ WINES GLASS"}},
        
        "vins_blancs_bouteille": {"section": "drinks", "name": {"fr": "VINS BLANCS BOUTEILLE", "en": "WHITE WINES BOTTLE"}},
        "vins_rouges_bouteille": {"section": "drinks", "name": {"fr": "VINS ROUGES BOUTEILLE", "en": "RED WINES BOTTLE"}},
        "vins_roses_bouteille": {"section": "drinks", "name": {"fr": "VINS ROSÉS BOUTEILLE", "en": "ROSÉ WINES BOTTLE"}},
        
        "vins_blancs_magnum": {"section": "drinks", "name": {"fr": "VINS BLANCS MAGNUM", "en": "WHITE WINES MAGNUM"}},
        "vins_rouges_magnum": {"section": "drinks", "name": {"fr": "VINS ROUGES MAGNUM", "en": "RED WINES MAGNUM"}},
        "vins_roses_magnum": {"section": "drinks", "name": {"fr": "VINS ROSÉS MAGNUM", "en": "ROSÉ WINES MAGNUM"}},
        
        "champagnes_coupe": {"section": "drinks", "name": {"fr": "CHAMPAGNES COUPE", "en": "CHAMPAGNES GLASS"}},
        "champagnes_bouteille": {"section": "drinks", "name": {"fr": "CHAMPAGNES BOUTEILLE", "en": "CHAMPAGNES BOTTLE"}},
        "champagnes_magnum": {"section": "drinks", "name": {"fr": "CHAMPAGNES MAGNUM", "en": "CHAMPAGNES MAGNUM"}},
        
        "aperitifs": {"section": "drinks", "name": {"fr": "APÉRITIFS", "en": "APERITIFS"}},
        "spritz": {"section": "drinks", "name": {"fr": "SPRITZ", "en": "SPRITZ"}},
        "cocktails": {"section": "drinks", "name": {"fr": "COCKTAILS", "en": "COCKTAILS"}},
        "mocktails": {"section": "drinks", "name": {"fr": "MOCKTAILS", "en": "MOCKTAILS"}},
        
        "rhums": {"section": "drinks", "name": {"fr": "RHUMS", "en": "RUMS"}},
        "vodkas": {"section": "drinks", "name": {"fr": "VODKAS", "en": "VODKAS"}},
        "gins": {"section": "drinks", "name": {"fr": "GINS", "en": "GINS"}},
        "tequilas": {"section": "drinks", "name": {"fr": "TEQUILAS", "en": "TEQUILAS"}},
        "whiskies": {"section": "drinks", "name": {"fr": "WHISKIES", "en": "WHISKIES"}},
        "digestifs": {"section": "drinks", "name": {"fr": "DIGESTIFS", "en": "DIGESTIFS"}},
        "cognacs_armagnacs": {"section": "drinks", "name": {"fr": "COGNACS & ARMAGNACS", "en": "COGNACS & ARMAGNACS"}}
    }
    
    current_id = 4000
    
    for category, items in menu_data.items():
        if category not in category_mapping:
            continue
        
        if not items or len(items) == 0:
            continue
            
        cat_info = category_mapping[category]
        section_type = cat_info["section"]
        
        category_section = {
            "name": cat_info["name"],
            "articles": []
        }
        
        for item in items:
            desc_value = item.get("description", False)
            desc_text = "" if (desc_value is False or not desc_value or desc_value == item["nom"]) else desc_value
            
            # ✅ NOUVEAU : Récupérer le chemin de l'image si elle existe
            item_image_path = ""
            if item_images and str(current_id) in item_images:
                item_image_path = item_images[str(current_id)]
            
            article = {
                "name": {"fr": item["nom"], "en": item["nom"]},
                "articleId": str(current_id),
                "posName": item["nom"],
                "price": {"priceId": "", "amount": float(item["prix"])},
                "img": item_image_path,  # ✅ MODIFIÉ : utiliser le chemin de l'image
                "descr": {"fr": desc_text, "en": desc_text},
                "allergens": {"fr": "", "en": ""},
                "additional": {"fr": "", "en": ""},
                "wine_pairing": {"fr": "", "en": ""},
                "options": [],
                "defaultCourseId": 1,
                "choicesForCourse": []
            }
            
            category_section["articles"].append(article)
            current_id += 1
        
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
            menu_data = clean_empty_categories(menu_data)  # ← AJOUTE cette ligne
            
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
    validated_menu: str = Form(None),
    item_images_json: str = Form(None)  # ✅ NOUVEAU paramètre
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
        
        # ✅✅✅ NOUVEAU CODE ICI ✅✅✅
        # Parser les images si elles existent
        item_images = {}
        if item_images_json:
            try:
                item_images = json.loads(item_images_json)
                print(f"✅ {len(item_images)} images de plats reçues")
            except:
                print("⚠️ Erreur parsing item_images_json")
                pass
        
        # Générer les fichiers avec les images
        backend_json = generate_backend_json(restaurant_name, qr_mode, address, version=1)
        backend_2_json = generate_backend_json(restaurant_name, qr_mode, address, version=2)
        menus_json = generate_menus_json(menu_data, backend_json["restaurantId"], item_images)  # ✅ MODIFIÉ : on passe item_images
        frontend_json = generate_frontend_json(restaurant_name, colors, version=1)
        frontend_2_json = generate_frontend_json(restaurant_name, colors, version=2)
        menus_2_json = menus_json.copy()
        # ✅✅✅ FIN DU NOUVEAU CODE ✅✅✅
        
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
                "total_articles": sum(len(v) for v in menu_data.values()),
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


@app.post("/upload-item-images")
async def upload_item_images(
    restaurant_name: str = Form(...),
    item_images_json: str = Form(...),  # JSON avec {itemId: file}
    ftp_password: str = Form(...),
    item_images: List[UploadFile] = File(...)
):
    """Upload les images des plats sur le serveur"""
    try:
        import paramiko
        
        SFTP_HOST = "178.32.198.72"
        SFTP_USER = "snadmin"
        
        # Connexion SFTP (port 22 pour les images)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=SFTP_HOST,
            port=22,
            username=SFTP_USER,
            password=ftp_password,
            timeout=30,
            look_for_keys=False,
            allow_agent=False
        )
        
        sftp = ssh.open_sftp()
        
        # Créer le dossier images si nécessaire
        IMAGES_PATH = "/var/www/pleazze/static/adel"
        try:
            parts = IMAGES_PATH.split('/')
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
        
        # Parser le JSON des correspondances
        item_images_map = json.loads(item_images_json)
        uploaded_paths = {}
        
        # Upload chaque image
        for i, image_file in enumerate(item_images):
            item_id = item_images_map.get(str(i))
            if not item_id:
                continue
            
            image_path = save_item_image(sftp, image_file.file, restaurant_name, item_id)
            if image_path:
                uploaded_paths[item_id] = image_path
        
        sftp.close()
        ssh.close()
        
        return {
            "success": True,
            "uploaded_images": uploaded_paths,
            "message": f"✅ {len(uploaded_paths)} images uploadées"
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

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
    restaurant_name: str = Form(...),
    backend_json: str = Form(...),
    backend_2_json: str = Form(...),
    frontend_json: str = Form(...),
    frontend_2_json: str = Form(...),
    menus_json: str = Form(...),
    menus_2_json: str = Form(...),
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
        
        # ✅ CONNEXION 1 : Port 2266 pour les JSON
        SFTP_HOST = "178.32.198.72"
        SFTP_USER = "snadmin"
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=SFTP_HOST, 
            port=2266,  # Port 2266 pour les JSON
            username=SFTP_USER, 
            password=ftp_password, 
            timeout=30,
            look_for_keys=False,
            allow_agent=False
        )
        
        sftp = ssh.open_sftp()
        
        CONFIG_PATH = f"/var/www/pleazze/data/config/abdel"
        CACHE_PATH = f"/var/www/pleazze/data/cache/abdel/data_2025-07-29_17-25-11"
        
        # Créer les dossiers pour JSON
        for path in [CONFIG_PATH, CACHE_PATH]:
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
            f.write(backend_2_json)

        with sftp.file(f'{CONFIG_PATH}/frontend.json', 'w') as f:
            f.write(frontend_json)

        with sftp.file(f'{CONFIG_PATH}/frontend_2.json', 'w') as f:
            f.write(frontend_2_json)

        # Upload JSON dans /cache/
        with sftp.file(f'{CACHE_PATH}/menus.4.json', 'w') as f:
            f.write(menus_json)

        with sftp.file(f'{CACHE_PATH}/menus_2.4.json', 'w') as f:
            f.write(menus_2_json)
        
        sftp.close()
        ssh.close()
        
        # ✅ CONNEXION 2 : Port 22 pour les images
        uploaded_images = []
        
        if home_banner or menu_banner:
            ssh_images = paramiko.SSHClient()
            ssh_images.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh_images.connect(
                hostname=SFTP_HOST,
                port=22,  # ✅ Port 22 pour les images
                username=SFTP_USER,
                password=ftp_password,
                timeout=30,
                look_for_keys=False,
                allow_agent=False
            )
            
            sftp_images = ssh_images.open_sftp()
            
            # ✅ Nouveau chemin selon Youri
            IMAGES_PATH = "/var/www/pleazze/static/adel"
            
            # Créer le dossier images
            try:
                parts = IMAGES_PATH.split('/')
                current = ''
                for part in parts:
                    if not part:
                        continue
                    current += '/' + part
                    try:
                        sftp_images.mkdir(current)
                    except:
                        pass
            except:
                pass
            
            safe_restaurant_name = restaurant_name.lower().replace(' ', '-').replace('/', '-')
            
            if home_banner:
                png_content = convert_to_png(home_banner.file)
                filename = f'home-banner-{safe_restaurant_name}.png'
                file_path = f'{IMAGES_PATH}/{filename}'
                
                with sftp_images.file(file_path, 'wb') as f:
                    f.write(png_content)
                
                sftp_images.chmod(file_path, 0o644)
                uploaded_images.append(filename)
            
            if menu_banner:
                png_content = convert_to_png(menu_banner.file)
                filename = f'menu-banner-{safe_restaurant_name}.png'
                file_path = f'{IMAGES_PATH}/{filename}'
                
                with sftp_images.file(file_path, 'wb') as f:
                    f.write(png_content)
                
                sftp_images.chmod(file_path, 0o644)
                uploaded_images.append(filename)
            
            sftp_images.close()
            ssh_images.close()
        
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
    

@app.post("/verify-uploaded-files")
async def verify_uploaded_files(
    restaurant_name: str = Form(...),
    ftp_password: str = Form(...)
):
    """Vérifie uniquement que les images sont bien uploadées"""
    try:
        import paramiko
        
        SFTP_HOST = "178.32.198.72"
        SFTP_USER = "snadmin"
        
        # ✅ Connexion sur port 22 pour vérifier les images
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=SFTP_HOST, 
            port=22,  # ✅ Port 22
            username=SFTP_USER, 
            password=ftp_password, 
            timeout=30,
            look_for_keys=False,
            allow_agent=False
        )
        
        sftp = ssh.open_sftp()
        
        # ✅ Nouveau chemin
        IMAGES_PATH = "/var/www/pleazze/static/adel"
        safe_restaurant_name = restaurant_name.lower().replace(' ', '-').replace('/', '-')
        
        results = {
            "success": True,
            "files_found": [],
            "files_missing": [],
            "file_details": [],
            "urls": []
        }
        
        # Vérifier home-banner
        home_banner_file = f'home-banner-{safe_restaurant_name}.png'
        try:
            file_stat = sftp.stat(f'{IMAGES_PATH}/{home_banner_file}')
            results["files_found"].append(home_banner_file)
            results["file_details"].append({
                "name": home_banner_file,
                "size": file_stat.st_size,
                "permissions": oct(file_stat.st_mode)[-3:]
            })
            results["urls"].append(f"https://preprod-pleazze.stepnet.fr/static/adel/{home_banner_file}")
        except FileNotFoundError:
            results["files_missing"].append(home_banner_file)
        
        # Vérifier menu-banner
        menu_banner_file = f'menu-banner-{safe_restaurant_name}.png'
        try:
            file_stat = sftp.stat(f'{IMAGES_PATH}/{menu_banner_file}')
            results["files_found"].append(menu_banner_file)
            results["file_details"].append({
                "name": menu_banner_file,
                "size": file_stat.st_size,
                "permissions": oct(file_stat.st_mode)[-3:]
            })
            results["urls"].append(f"https://preprod-pleazze.stepnet.fr/static/adel/{menu_banner_file}")
        except FileNotFoundError:
            results["files_missing"].append(menu_banner_file)
        
        sftp.close()
        ssh.close()
        
        return results
        
    except Exception as e:
        return {"success": False, "error": str(e)}

def save_item_image(sftp, image_file, restaurant_name: str, item_id: str) -> str:
    """Sauvegarde une image de plat et retourne le chemin"""
    try:
        from PIL import Image
        import io
        
        # Convertir en PNG
        image_bytes = image_file.read()
        image = Image.open(io.BytesIO(image_bytes))
        png_buffer = io.BytesIO()
        image.save(png_buffer, format='PNG')
        png_buffer.seek(0)
        
        # Créer le nom de fichier
        safe_restaurant_name = restaurant_name.lower().replace(' ', '-').replace('/', '-')
        filename = f'item-{safe_restaurant_name}-{item_id}.png'
        
        # Chemin sur le serveur
        IMAGES_PATH = "/var/www/pleazze/static/adel"
        file_path = f'{IMAGES_PATH}/{filename}'
        
        # Upload
        with sftp.file(file_path, 'wb') as f:
            f.write(png_buffer.getvalue())
        
        sftp.chmod(file_path, 0o644)
        
        # Retourner le chemin relatif pour le JSON
        return f"/static/adel/{filename}"
        
    except Exception as e:
        print(f"Erreur sauvegarde image item {item_id}: {str(e)}")
        return ""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
