from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import fitz  # PyMuPDF
import json
import os
from groq import Groq
from typing import Dict
import requests
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Restaurant Menu Generator API", version="2.0")

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En production, remplace par ton domaine WordPress
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialiser le client Groq
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("⚠️  GROQ_API_KEY non définie dans .env")

groq_client = Groq(api_key=GROQ_API_KEY)

# Configuration Odoo (à remplir)
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
    {{"nom": "Soupe à l'oignon", "prix": 8.50, "tva": "10%"}},
    {{"nom": "Salade César", "prix": 12.00, "tva": "10%", "description": "Salade verte, tomates, poulet frit"}}
  ],
  "plats": [
    {{"nom": "Steak frites", "prix": 22.00, "tva": "10%"}},
    {{"nom": "Saumon grillé", "prix": 24.50, "tva": "10%"}}
  ],
  "desserts": [
    {{"nom": "Tarte tatin", "prix": 7.50, "tva": "10%", "description": "Tarte aux pommes de saison"}},
    {{"nom": "Crème brûlée", "prix": 8.00, "tva": "10%"}}
  ],
  "boissons_soft": [
    {{"nom": "Coca-Cola", "prix": 4.50, "tva": "10%"}},
    {{"nom": "Eau minérale", "prix": 3.50, "tva": "10%"}}
  ],
  "boissons_alcoolisees": [
    {{"nom": "Vin rouge (verre)", "prix": 6.00, "tva": "20%"}},
    {{"nom": "Bière pression", "prix": 5.50, "tva": "20%"}}
  ]
}}

RÈGLES:
- N'utilise JAMAIS de guillemets dans les noms de plats (remplace " par ')
- Assure-toi que le JSON est valide et bien formaté
- Extrais TOUS les plats et boissons avec leurs prix
- Tu peux créer d'autres catégories si nécessaire ("A partager", "Cocktails", etc.)
- Si un prix a une virgule (12,50), convertis en point (12.50)
- Ajoute le champ "description" quand c'est pertinent
- Si plusieurs variantes d'un produit (ex: "jus pressé, orange, citron"), crée 2 produits distincts
- Classe chaque item dans la bonne catégorie
- TVA: 10% pour nourriture/soft, 20% pour alcool
- Retourne UNIQUEMENT le JSON, rien d'autre"""

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=10000
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Nettoyer le JSON
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]
        
        # Parser le JSON
        menu_json = json.loads(response_text)
        return menu_json
        
    except json.JSONDecodeError as e:
        print(f"⚠️  JSON invalide reçu de Groq")
        print(f"Réponse brute:\n{response_text}\n")
        raise HTTPException(status_code=500, detail=f"Erreur parsing JSON: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur Groq API: {str(e)}")


def create_restaurant_in_odoo(restaurant_data: Dict) -> Dict:
    """Crée un restaurant dans Odoo"""
    if not ODOO_PASSWORD:
        return {"success": False, "message": "Odoo non configuré"}
    
    try:
        # 1. Authentification Odoo
        auth_url = f"{ODOO_URL}/web/session/authenticate"
        auth_data = {
            "jsonrpc": "2.0",
            "params": {
                "db": ODOO_DB,
                "login": ODOO_USERNAME,
                "password": ODOO_PASSWORD
            }
        }
        
        session = requests.Session()
        auth_response = session.post(auth_url, json=auth_data)
        
        if auth_response.status_code != 200:
            return {"success": False, "message": "Échec authentification Odoo"}
        
        # 2. Créer le restaurant (res.partner)
        create_url = f"{ODOO_URL}/web/dataset/call_kw"
        create_data = {
            "jsonrpc": "2.0",
            "params": {
                "model": "res.partner",
                "method": "create",
                "args": [{
                    "name": restaurant_data["restaurant"],
                    "is_company": True,
                    "customer_rank": 1,
                    # Ajoute d'autres champs selon ton modèle Odoo
                }],
                "kwargs": {}
            }
        }
        
        create_response = session.post(create_url, json=create_data)
        result = create_response.json()
        
        if "result" in result:
            partner_id = result["result"]
            return {
                "success": True,
                "partner_id": partner_id,
                "message": f"Restaurant créé dans Odoo (ID: {partner_id})"
            }
        else:
            return {"success": False, "message": "Erreur création restaurant"}
            
    except Exception as e:
        return {"success": False, "message": f"Erreur Odoo: {str(e)}"}


@app.get("/")
def home():
    return {
        "message": "🍽️ API Restaurant Menu Generator",
        "version": "2.0",
        "endpoints": {
            "/generate-menu": "POST - Génère le JSON depuis un PDF",
            "/create-odoo": "POST - Crée le restaurant dans Odoo",
            "/health": "GET - Vérifie la santé de l'API"
        }
    }


@app.post("/generate-menu")
async def generate_menu(
    restaurant_name: str = Form(...),
    color1: str = Form(...),
    color2: str = Form(...),
    color3: str = Form(...),
    menu_file: UploadFile = File(...),
    create_in_odoo: bool = Form(False)
):
    """Génère un JSON structuré à partir d'un PDF de menu"""
    try:
        # Vérifier que c'est bien un PDF
        if not menu_file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Le fichier doit être un PDF")
        
        # Lire le contenu du PDF
        pdf_content = await menu_file.read()
        
        # Extraire le texte
        text = extract_text_from_pdf(pdf_content)
        
        if not text.strip():
            raise HTTPException(status_code=400, detail="Impossible d'extraire du texte du PDF")
        
        print(f"✅ Texte extrait: {len(text)} caractères")
        
        # Classifier avec Groq
        menu_classifie = classify_menu_with_groq(text)
        
        # Créer le JSON final
        resultat = {
            "restaurant": restaurant_name,
            "couleurs": [color1, color2, color3],
            "menu": menu_classifie,
            "stats": {
                "total_items": sum(len(v) for v in menu_classifie.values()),
                "entrees": len(menu_classifie.get("entrees", [])),
                "plats": len(menu_classifie.get("plats", [])),
                "desserts": len(menu_classifie.get("desserts", [])),
                "boissons_soft": len(menu_classifie.get("boissons_soft", [])),
                "boissons_alcoolisees": len(menu_classifie.get("boissons_alcoolisees", []))
            }
        }
        
        # Créer dans Odoo si demandé
        odoo_result = None
        if create_in_odoo:
            odoo_result = create_restaurant_in_odoo(resultat)
            resultat["odoo"] = odoo_result
        
        return {
            "success": True,
            "data": json.dumps(resultat, indent=2, ensure_ascii=False),
            "odoo": odoo_result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")


@app.post("/create-odoo")
async def create_in_odoo_only(restaurant_data: Dict):
    """Crée uniquement le restaurant dans Odoo"""
    result = create_restaurant_in_odoo(restaurant_data)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@app.get("/health")
def health_check():
    """Vérifie que l'API est opérationnelle"""
    groq_status = "✅ OK" if GROQ_API_KEY else "❌ GROQ_API_KEY non définie"
    odoo_status = "✅ Configuré" if ODOO_PASSWORD else "⚠️  Non configuré"
    
    return {
        "status": "running",
        "groq": groq_status,
        "odoo": odoo_status,
        "version": "2.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)