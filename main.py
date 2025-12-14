def generate_menus_json(menu_data: Dict, restaurant_id: str) -> Dict:
    """Génère le fichier menus.4.json au format exact du restaurant"""
    
    menus_json = {
        "menus": [],
        "sections": [],
        "drinks": []
    }
    
    current_id = 3000
    
    # Fonction helper pour créer un article
    def create_article(item, article_id):
        return {
            "name": {"fr": item["nom"], "en": item["nom"]},
            "articleId": str(article_id),
            "posName": item["nom"],
            "price": {"priceId": "", "amount": float(item["prix"])},
            "img": "",
            "descr": {"fr": item.get("description", False), "en": item.get("description", False)},
            "allergens": {"fr": "", "en": ""},
            "additional": {"fr": "", "en": ""},
            "wine_pairing": {"fr": "", "en": ""},
            "options": [],
            "defaultCourseId": 1,
            "choicesForCourse": []
        }
    
    # ========== SECTIONS (NOURRITURE) ==========
    food_mapping = {
        "planches": {"name": {"fr": "SNACKING", "en": "SNACKING"}},
        "tapas": {"name": {"fr": "SNACKING", "en": "SNACKING"}},
        "entrees": {"name": {"fr": "ENTRÉES", "en": "STARTERS"}},
        "salades": {"name": {"fr": "SALADES", "en": "SALADS"}},
        "plats": {"name": {"fr": "PLATS", "en": "MAINS"}},
        "desserts": {"name": {"fr": "DESSERTS", "en": "DESSERTS"}},
        "pinsa_pizza": {"name": {"fr": "PINSA & PIZZA", "en": "PINSA & PIZZA"}},
        "pates": {"name": {"fr": "PÂTES", "en": "PASTA"}}
    }
    
    # Regrouper planches + tapas ensemble
    snacking_items = []
    if menu_data.get('planches'):
        snacking_items.extend(menu_data['planches'])
    if menu_data.get('tapas'):
        snacking_items.extend(menu_data['tapas'])
    
    if snacking_items:
        section = {
            "name": {"fr": "SNACKING", "en": "SNACKING"},
            "articles": []
        }
        for item in snacking_items:
            section["articles"].append(create_article(item, current_id))
            current_id += 1
        menus_json["sections"].append(section)
    
    # Autres catégories food (sauf planches/tapas déjà traités)
    for category in ['entrees', 'salades', 'plats', 'desserts', 'pinsa_pizza', 'pates']:
        if menu_data.get(category):
            section = {
                "name": food_mapping[category]["name"],
                "articles": []
            }
            for item in menu_data[category]:
                section["articles"].append(create_article(item, current_id))
                current_id += 1
            menus_json["sections"].append(section)
    
    # ========== DRINKS ==========
    
    # 1. COCKTAILS
    if menu_data.get('cocktails'):
        section = {
            "name": {"fr": "COCKTAILS", "en": "COCKTAILS"},
            "articles": []
        }
        for item in menu_data['cocktails']:
            section["articles"].append(create_article(item, current_id))
            current_id += 1
        menus_json["drinks"].append(section)
    
    # 2. MOCKTAILS
    if menu_data.get('mocktails'):
        section = {
            "name": {"fr": "MOCKTAILS", "en": "MOCKTAILS"},
            "articles": []
        }
        for item in menu_data['mocktails']:
            section["articles"].append(create_article(item, current_id))
            current_id += 1
        menus_json["drinks"].append(section)
    
    # 3. APÉRITIFS (+ spritz si existe)
    aperitifs_items = []
    if menu_data.get('aperitifs'):
        aperitifs_items.extend(menu_data['aperitifs'])
    if menu_data.get('spritz'):
        aperitifs_items.extend(menu_data['spritz'])
    
    if aperitifs_items:
        section = {
            "name": {"fr": "APÉRITIFS", "en": "APERITIFS"},
            "articles": []
        }
        for item in aperitifs_items:
            section["articles"].append(create_article(item, current_id))
            current_id += 1
        menus_json["drinks"].append(section)
    
    # 4. BIÈRES (avec sous-sections)
    bieres_pression = menu_data.get('bieres_pression', [])
    bieres_bouteilles = menu_data.get('bieres_bouteilles', [])
    
    if bieres_pression or bieres_bouteilles:
        section = {
            "name": {"fr": "BIÈRES", "en": "BEERS"},
            "sections": []
        }
        
        if bieres_pression:
            subsection = {
                "name": {"fr": "Pression", "en": "Pression"},
                "articles": []
            }
            for item in bieres_pression:
                subsection["articles"].append(create_article(item, current_id))
                current_id += 1
            section["sections"].append(subsection)
        
        if bieres_bouteilles:
            subsection = {
                "name": {"fr": "Bouteilles", "en": "Bouteilles"},
                "articles": []
            }
            for item in bieres_bouteilles:
                subsection["articles"].append(create_article(item, current_id))
                current_id += 1
            section["sections"].append(subsection)
        
        menus_json["drinks"].append(section)
    
    # 5. SOFTS-EAUX (+ jus)
    softs_items = []
    if menu_data.get('boissons_soft'):
        softs_items.extend(menu_data['boissons_soft'])
    if menu_data.get('jus'):
        softs_items.extend(menu_data['jus'])
    
    if softs_items:
        section = {
            "name": {"fr": "SOFTS-EAUX", "en": "SOFT DRINKS"},
            "articles": []
        }
        for item in softs_items:
            section["articles"].append(create_article(item, current_id))
            current_id += 1
        menus_json["drinks"].append(section)
    
    # 6. CAFÉTERIE
    if menu_data.get('boissons_chaudes'):
        section = {
            "name": {"fr": "CAFÉTERIE", "en": "CAFE"},
            "articles": []
        }
        for item in menu_data['boissons_chaudes']:
            section["articles"].append(create_article(item, current_id))
            current_id += 1
        menus_json["drinks"].append(section)
    
    # 7. VINS VERRE BLANCS
    if menu_data.get('vins_blancs_verre'):
        section = {
            "name": {"fr": "VINS VERRE BLANCS", "en": "WHITE WINES GLASS"},
            "articles": []
        }
        for item in menu_data['vins_blancs_verre']:
            section["articles"].append(create_article(item, current_id))
            current_id += 1
        menus_json["drinks"].append(section)
    
    # 8. VINS VERRE ROUGES
    if menu_data.get('vins_rouges_verre'):
        section = {
            "name": {"fr": "VINS VERRE ROUGES", "en": "RED WINES GLASS"},
            "articles": []
        }
        for item in menu_data['vins_rouges_verre']:
            section["articles"].append(create_article(item, current_id))
            current_id += 1
        menus_json["drinks"].append(section)
    
    # 9. VINS VERRE ROSÉS
    if menu_data.get('vins_roses_verre'):
        section = {
            "name": {"fr": "VINS VERRE ROSÉS", "en": "ROSÉ WINES GLASS"},
            "articles": []
        }
        for item in menu_data['vins_roses_verre']:
            section["articles"].append(create_article(item, current_id))
            current_id += 1
        menus_json["drinks"].append(section)
    
    # 10. CHAMPAGNES BLANCS (coupe + bouteille)
    champagnes_blancs = []
    if menu_data.get('champagnes_coupe'):
        champagnes_blancs.extend(menu_data['champagnes_coupe'])
    if menu_data.get('champagnes_bouteille'):
        champagnes_blancs.extend(menu_data['champagnes_bouteille'])
    
    if champagnes_blancs:
        section = {
            "name": {"fr": "CHAMPAGNES BLANCS", "en": "CHAMPAGNES WHITE"},
            "articles": []
        }
        for item in champagnes_blancs:
            section["articles"].append(create_article(item, current_id))
            current_id += 1
        menus_json["drinks"].append(section)
    
    # 11. CHAMPAGNES ROSÉ (magnum)
    if menu_data.get('champagnes_magnum'):
        section = {
            "name": {"fr": "CHAMPAGNES ROSÉ", "en": "CHAMPAGNES ROSÉ"},
            "articles": []
        }
        for item in menu_data['champagnes_magnum']:
            section["articles"].append(create_article(item, current_id))
            current_id += 1
        menus_json["drinks"].append(section)
    
    # 12. ALCOOLS (TOUS LES SPIRITUEUX REGROUPÉS)
    alcools_items = []
    for category in ['rhums', 'vodkas', 'gins', 'tequilas', 'whiskies', 'digestifs', 'cognacs_armagnacs']:
        if menu_data.get(category):
            alcools_items.extend(menu_data[category])
    
    if alcools_items:
        section = {
            "name": {"fr": "ALCOOLS", "en": "SPIRITS"},
            "articles": []
        }
        for item in alcools_items:
            section["articles"].append(create_article(item, current_id))
            current_id += 1
        menus_json["drinks"].append(section)
    
    # 13. BT VINS BLANCS (avec sous-sections par région)
    vins_blancs_bt = menu_data.get('vins_blancs_bouteille', [])
    if vins_blancs_bt:
        section = {
            "name": {"fr": "BT VINS BLANCS", "en": "WHITE WINES BOTTLE"},
            "sections": []
        }
        
        # Regrouper par région (simplifié - tu peux affiner)
        regions = {}
        for item in vins_blancs_bt:
            # Déterminer la région depuis le nom
            nom = item['nom'].lower()
            if 'languedoc' in nom or 'viognier' in nom:
                region = 'LE LANGUEDOC'
            elif 'bourgogne' in nom or 'chablis' in nom or 'beaune' in nom:
                region = 'LA BOURGOGNE'
            elif 'loire' in nom or 'sancerre' in nom or 'pouilly' in nom:
                region = 'LA LOIRE'
            elif 'rhône' in nom or 'condrieu' in nom:
                region = 'LE RHÔNE'
            else:
                region = 'AUTRES'
            
            if region not in regions:
                regions[region] = []
            regions[region].append(item)
        
        for region_name, items in regions.items():
            subsection = {
                "name": {"fr": region_name, "en": region_name},
                "articles": []
            }
            for item in items:
                subsection["articles"].append(create_article(item, current_id))
                current_id += 1
            section["sections"].append(subsection)
        
        menus_json["drinks"].append(section)
    
    # 14. BT VINS ROSÉS (avec sous-sections)
    vins_roses_bt = menu_data.get('vins_roses_bouteille', [])
    if vins_roses_bt:
        section = {
            "name": {"fr": "BT VINS ROSÉS", "en": "ROSÉ WINES BOTTLE"},
            "sections": [{
                "name": {"fr": "La PROVENCE", "en": "La PROVENCE"},
                "articles": []
            }]
        }
        for item in vins_roses_bt:
            section["sections"][0]["articles"].append(create_article(item, current_id))
            current_id += 1
        menus_json["drinks"].append(section)
    
    # 15. BT VINS ROUGES (avec sous-sections par région)
    vins_rouges_bt = menu_data.get('vins_rouges_bouteille', [])
    if vins_rouges_bt:
        section = {
            "name": {"fr": "BT VINS ROUGES", "en": "RED WINES BOTTLE"},
            "sections": []
        }
        
        regions = {}
        for item in vins_rouges_bt:
            nom = item['nom'].lower()
            if 'bourgogne' in nom or 'gevrey' in nom or 'mercurey' in nom or 'beaune' in nom:
                region = 'LA BOURGOGNE'
            elif 'rhône' in nom or 'châteauneuf' in nom or 'crozes' in nom or 'vacqueras' in nom:
                region = 'LE RHÔNE'
            elif 'bordeaux' in nom or 'médoc' in nom or 'saint-julien' in nom or 'morgon' in nom:
                region = 'BORDEAUX'
            else:
                region = 'AUTRES'
            
            if region not in regions:
                regions[region] = []
            regions[region].append(item)
        
        for region_name, items in regions.items():
            subsection = {
                "name": {"fr": region_name, "en": region_name},
                "articles": []
            }
            for item in items:
                subsection["articles"].append(create_article(item, current_id))
                current_id += 1
            section["sections"].append(subsection)
        
        menus_json["drinks"].append(section)
    
    return menus_json
