#!/usr/bin/env python3
import httpx
import random
import string
from datetime import datetime, timezone
import os

AUTH_HEADERS = {}

USERS_API = "http://localhost:8000"
ITEMS_API = "http://localhost:8001"
COMPETENCIES_API = "http://localhost:8003"
CV_API = "http://localhost:8004"
PROMPTS_API = "http://localhost:8005"

FIRST_NAMES = ["Alice", "Bob", "Charlie", "David", "Emma", "Frank", "Grace", "Henry", "Isabel", "Jack", "Karl", "Laura"]
LAST_NAMES = ["Martin", "Bernard", "Thomas", "Petit", "Robert", "Richard", "Durand", "Dubois", "Moreau", "Laurent", "Simon", "Michel"]
CATEGORIES_LIST = [
    ("Électronique", "Appareils, gadgets et hardware"),
    ("Mobilier", "Bureaux, chaises et aménagement"),
    ("Logiciel", "Licences, abonnements et outils SaaS"),
    ("Matériel", "Fournitures et consommables"),
    ("Services", "Consulting, maintenance et support"),
    ("Formation", "Cours, certifications et e-learning"),
    ("Cloud", "Infrastructure, stockage et serveurs")
]

COMPETENCIES_ZENIKA_TREE = {
    "Architecture & Craft": {
        "description": "Excellence logicielle et conception",
        "sub": {
            "Langages Backend": {
                "description": "Développement et programmation côté serveur",
                "sub": [
                    ("Java", "Maîtrise de l'écosystème JVM"),
                    ("Python", "Développement backend et scripts d'IA")
                ]
            },
            "Langages Frontend": {
                "description": "Développement d'interfaces asynchrones",
                "sub": [
                    ("Vue.js", "Développement frontend moderne"),
                    ("TypeScript", "Typage strict du code client")
                ]
            }
        }
    },
    "Data & IA": {
        "description": "Valorisation des données et Intelligence Artificielle",
        "sub": {
            "Ingénierie des données": {
                "description": "Pipelines et ingénierie de données",
                "sub": [
                    ("SQL", "Bases de données relationnelles"),
                    ("Spark", "Traitement de données distribuées")
                ]
            },
            "Modélisation Automatique": {
                "description": "Algorithmes prédictifs et Machine Learning",
                "sub": [
                    ("TensorFlow", "Modélisation de réseaux de neurones")
                ]
            }
        }
    },
    "Cloud & DevOps": {
        "description": "Infrastructures cloud et automatisation continue",
        "sub": {
            "Conteneurisation": {
                "description": "Isolation et orchestration de processus",
                "sub": [
                    ("Docker", "Runtime et build d'images"),
                    ("Kubernetes", "Déploiement de clusters à l'échelle")
                ]
            },
            "Automatisation Avancée": {
                "description": "Fiabilisation des tests et infrastructures",
                "sub": [
                    ("CI/CD", "Pipelines de livraison continues"),
                    ("Terraform", "Infrastructure as Code (IaC)")
                ]
            }
        }
    }
}

def get_db_url(dbname):
    base_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
    if "?" in base_url:
        uri, params = base_url.split("?")
        uri = uri.rsplit("/", 1)[0] + "/" + dbname
        return f"{uri}?{params}"
    else:
        return base_url.rsplit("/", 1)[0] + "/" + dbname

def random_string(length=8):
    return ''.join(random.choices(string.ascii_lowercase, k=length))

def create_category(name, description):
    # Pre-check existence
    try:
        categories = httpx.get(f"{ITEMS_API}/categories", headers=AUTH_HEADERS).json()
        for c in categories:
            if c['name'] == name:
                print(f"  - Category {name} already exists. Skipping.")
                return c
    except: pass

    data = {"name": name, "description": description}
    try:
        response = httpx.post(f"{ITEMS_API}/categories", json=data, headers=AUTH_HEADERS)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"  ❌ Error creating category {name}: {str(e)}")
        raise

def create_competency(name, description, parent_id=None):

    data = {"name": name, "description": description}
    if parent_id is not None:
        data["parent_id"] = parent_id
        
    try:
        response = httpx.post(f"{COMPETENCIES_API}/", json=data, headers=AUTH_HEADERS)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"  ❌ Error creating competency {name}: {str(e)}")
        raise

def assign_competency(user_id, comp_id):
    try:
        response = httpx.post(f"{COMPETENCIES_API}/user/{user_id}/assign/{comp_id}", headers=AUTH_HEADERS)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"  - Error assigning competency {comp_id} to user {user_id}: {str(e)}")
        return None

def import_cv(url):
    try:
        response = httpx.post(f"{CV_API}/import", json={"url": url}, headers=AUTH_HEADERS, timeout=60.0)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"  ❌ Error importing CV {url}: {str(e)}")
        return None

def create_user(first, last, allowed_category_ids=None):
    if allowed_category_ids is None:
        allowed_category_ids = []
    username = f"{first[0].lower()}{last.lower()}{random.randint(10, 99)}"
    email = f"{first.lower()}.{last.lower()}@zenika.com"
    
    # Check if user exists by email or username search
    try:
        search_res = httpx.get(f"{USERS_API}/", params={"skip": 0, "limit": 100}, headers=AUTH_HEADERS)
        if search_res.status_code == 200:
            data = search_res.json()
            users_list = data.get("items", []) if isinstance(data, dict) else data
            for u in users_list:
                if u['email'] == email or u['username'] == username:
                    print(f"  - User {email} already exists. Skipping.")
                    return u
    except Exception as e:
        print(f"  - Error checking existing user {email}: {str(e)}")

    data = {
        "username": username,
        "email": email,
        "first_name": first,
        "last_name": last,
        "full_name": f"{first} {last}",
        "password": "zenika123",
        "allowed_category_ids": allowed_category_ids
    }
    response = httpx.post(f"{USERS_API}/", json=data, headers=AUTH_HEADERS)
    if response.status_code >= 400:
        print(f"  ❌ Error creating user {username}: {response.status_code} - {response.text}")
        response.raise_for_status()
    return response.json()

def create_item(user_id, category_ids):
    item_names = ["Laptop", "Monitor", "Keyboard", "Mouse", "Desk", "Chair", "License", "Server", "Consulting", "Workshop"]
    name = f"{random.choice(item_names)} {random_string(4).upper()}"
    data = {
        "name": name,
        "description": f"Standard {name.lower()} for professional use.",
        "user_id": user_id,
        "category_ids": category_ids
    }
    response = httpx.post(f"{ITEMS_API}/", json=data, headers=AUTH_HEADERS)
    response.raise_for_status()
    return response.json()

def main():
    print("🚀 Starting Zenika Seed Data Process...\n")

    print("🔑 Connecting to DB recursively to insert Root Admin...")
    db_url = get_db_url("users")
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        # Stable bcrypt hash for 'admin'
        admin_hash = "$2b$12$DmcLZx/FfS5ZVVpGVbYOZOM6a27EsafCWBmc26RTxfY5mnn0o/Usi"
        # Removed DDL/ALTER TABLE since Liquibase handles schema management natively
        
        cur.execute("SELECT id FROM users WHERE username = 'admin'")
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO users (username, email, first_name, last_name, full_name, hashed_password, role, is_active, allowed_category_ids, created_at)
                VALUES ('admin', 'admin@zenika.com', 'Zenika', 'Admin', 'Zenika Admin', %s, 'admin', True, '1,2,3,4,5', %s)
            """, (admin_hash, datetime.now(timezone.utc)))
            conn.commit()
            print("  - Admin inserted directly via SQL.")
        else:
            print("  - Admin user already exists in DB.")

        cur.execute("SELECT id FROM users WHERE email = 'sebastien.lavayssiere@zenika.com'")
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO users (username, email, first_name, last_name, full_name, hashed_password, role, is_active, created_at)
                VALUES ('slavayssiere', 'sebastien.lavayssiere@zenika.com', 'Sébastien', 'Lavayssière', 'Sébastien Lavayssière', %s, 'admin', True, %s)
            """, (admin_hash, datetime.now(timezone.utc)))
            conn.commit()
            print("  - Sébastien Lavayssière (slavayssiere) added as admin via SQL.")
        else:
            print("  - Sébastien Lavayssière already exists in DB.")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"  - Database injection failed: {str(e)}")

    print("\n🔐 Authenticating Admin securely to retrieve JWT...")
    try:
        login_res = httpx.post(
            f"{USERS_API}/login", 
            json={"email": "admin@zenika.com", "password": "admin"}
        )
        if login_res.status_code == 200:
            token = login_res.json().get("access_token")
            global AUTH_HEADERS
            AUTH_HEADERS = {"Authorization": f"Bearer {token}"}
            print("  - Authenticated successfully. JWT Captured.")
        else:
            print(f"  ❌ Admin login failed! HTTP {login_res.status_code}")
            return
    except Exception as e:
        print(f"  ❌ Error requesting JWT: {str(e)}")
        return

    print("\n📁 Seeding Categories...")
    category_ids = []
    for name, desc in CATEGORIES_LIST:
        cat = create_category(name, desc)
        category_ids.append(cat['id'])
        print(f"  - Created category: {name} (ID={cat['id']})")

        # Create the dedicated user for this category
        clean_name = name.lower().replace("é", "e").replace(" ", "")
        cat_user_data = {
            "username": clean_name,
            "email": f"{clean_name}@zenika.com",
            "first_name": name,
            "last_name": "Catégorie",
            "full_name": f"Manager {name}",
            "password": name,
            "allowed_category_ids": [cat['id']]
        }
        try:
            res = httpx.post(f"{USERS_API}/", json=cat_user_data, headers=AUTH_HEADERS)
            if res.status_code in [200, 201]:
                print(f"    ↳ Created manager user: {clean_name} (password: {name})")
        except Exception as e:
            print(f"    ↳ Error creating manager {clean_name}: {str(e)}")

    print("\n🔄 Upgrading Admin Category Permissions dynamically via SQL...")
    try:
        import psycopg2
        db_url = get_db_url("users")
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        ids_str = ",".join(map(str, category_ids))
        cur.execute("UPDATE users SET allowed_category_ids = %s WHERE email = 'admin@zenika.com'", (ids_str,))
        conn.commit()
        cur.close()
        conn.close()
        
        login_res = httpx.post(
            f"{USERS_API}/login", 
            json={"email": "admin@zenika.com", "password": "admin"}
        )
        if login_res.status_code == 200:
            token = login_res.json().get("access_token")
            AUTH_HEADERS["Authorization"] = f"Bearer {token}"
            print("  - Admin payload re-baked successfully.")
        else:
            print(f"  ❌ Admin re-authentication failed! HTTP {login_res.status_code}")
    except Exception as e:
        print(f"  ❌ Error upgrading admin permissions: {str(e)}")

    print("\n👤 Seeding 12 Zenika Users with Permissions...")
    users = []
    for i in range(12):
        first = FIRST_NAMES[i]
        last = LAST_NAMES[i]
        # Assign 3 to 5 random categories as allowed
        user_allowed_cats = random.sample(category_ids, k=random.randint(3, 5))
        user = create_user(first, last, user_allowed_cats)
        users.append(user)
        print(f"  - Created user: {user['full_name']} (Allowed Cats: {len(user['allowed_category_ids'])})")

    print("\n📦 Seeding 50 Tagged Items (Respecting Permissions)...")
    for i in range(50):
        user = random.choice(users)
        # Randomly assign 1 to 2 categories from the user's ALLOWED ones
        item_categories = random.sample(user['allowed_category_ids'], k=random.randint(1, min(2, len(user['allowed_category_ids']))))
        item = create_item(user['id'], item_categories)
        print(f"  - Created item {i+1}/50: {item['name']} (assigned to {user['username']})")

    print("\n🛠️ Seeding Competencies (Cleaning legacy flats...)")
    try:
        import psycopg2
        db_url = get_db_url("competencies")
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE competencies CASCADE;")
        conn.commit()
        cur.close()
        conn.close()
        print("  - Table 'competencies' successfully truncated.")
    except Exception as e:
        print(f"  ❌ Error truncating competencies: {str(e)}")

    comp_ids = []
    
    def seed_tree(nodes, parent_id=None, level=1):
        if isinstance(nodes, dict):
            for name, content in nodes.items():
                desc = content["description"]
                comp = create_competency(name, desc, parent_id)
                comp_ids.append(comp['id'])
                indent = "  " * level
                print(f"{indent}- Created Level {level}: {name} (ID={comp['id']})")
                if "sub" in content:
                    seed_tree(content["sub"], comp['id'], level + 1)
        elif isinstance(nodes, list):
            for name, desc in nodes:
                comp = create_competency(name, desc, parent_id)
                comp_ids.append(comp['id'])
                indent = "  " * level
                print(f"{indent}- Created Leaf: {name} (ID={comp['id']})")

    seed_tree(COMPETENCIES_ZENIKA_TREE)

    print("\n📄 Loading External AI Prompts into Gateway...")
    prompt_files = {
        "agent_api.assistant_system_instruction": "agent_api/agent_api.assistant_system_instruction.txt",
        "agent_api.capabilities_instruction": "agent_api/agent_api.capabilities_instruction.txt",
        "cv_api.extract_cv_info": "cv_api/cv_api.extract_cv_info.txt",
        "cv_api.generate_taxonomy_tree": "cv_api/cv_api.generate_taxonomy_tree.txt"
    }
    for key, path in prompt_files.items():
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            res = httpx.put(f"{PROMPTS_API}/{key}", json={"value": content}, headers=AUTH_HEADERS)
            if res.status_code < 400:
                print(f"  - Successfully seeded prompt '{key}'")
            else:
                print(f"  ❌ Failed seeding prompt '{key}': HTTP {res.status_code} - {res.text}")
        except Exception as e:
            print(f"  ❌ Error reading prompt '{key}': {e}")

    print("\n🎯 Assigning Competencies to Users...")
    for user in users:
        # Assign 2 to 4 random competencies to each user
        assigned = random.sample(comp_ids, k=random.randint(2, 4))
        for cid in assigned:
            assign_competency(user['id'], cid)
        print(f"  - Assigned {len(assigned)} competencies to {user['username']}")

    print("\n📄 Importing Initial Candidate CVs via RAG pipeline...")
    cv_urls = [
        "https://docs.google.com/document/d/1bIGg-17JMj9t7hO8jtB5G88yfF6eFJI-4vHiI1I4x3s/edit",
        "https://docs.google.com/document/d/1SxWW-HN-cxGXBFerPRtvQpzfFKhKkKov/edit"
    ]
    for url in cv_urls:
        print(f"  - Triggering Vectorial RAG Indexing for: {url}")
        res = import_cv(url)
        if res:
            print(f"    ↳ Successfully imported CV mapping to User ID {res.get('user_id')} (Mapped {res.get('competencies_assigned')} competencies)")

    
    print("\n📁 Seeding Drive Folders for CV Intake...")
    try:
        import psycopg2
        db_url = get_db_url("drive")
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        # Seed the Niort folder
        cur.execute("SELECT id FROM drive_folders WHERE google_folder_id = '1WdjkhFc41wYxU3KgirDUH6xYWDSFkDin'")
        if not cur.fetchone():
            from datetime import datetime, timezone
            cur.execute("""
                INSERT INTO drive_folders (google_folder_id, tag, created_at)
                VALUES ('1WdjkhFc41wYxU3KgirDUH6xYWDSFkDin', 'Niort', %s)
            """, (datetime.now(timezone.utc),))
            conn.commit()
            print("  - Inserted Drive mapping for 'Niort'.")
        else:
            print("  - Drive mapping 'Niort' already exists.")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"  - Error seeding drive folder: {e}")

    print("\n✨ Done! Zenika Seed process complete.")

if __name__ == "__main__":
    main()
