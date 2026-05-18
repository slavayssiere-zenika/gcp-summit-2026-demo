#!/usr/bin/env python3
import json
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

# Referentiel partage avec locust/locustfile.py
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "locust", "data")
_TEST_DATA_PATH = os.path.join(_DATA_DIR, "test_data.json")
_SEEDED_IDS_PATH = os.path.join(_DATA_DIR, "seeded_ids.json")

with open(_TEST_DATA_PATH, encoding="utf-8") as _f:
    _TEST_DATA = json.load(_f)

FIRST_NAMES = _TEST_DATA["first_names"]
LAST_NAMES = _TEST_DATA["last_names"]
CATEGORIES_LIST = [tuple(c.values()) for c in _TEST_DATA["categories"]]

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
    # Pre-check existence - reponse paginee {"items": [...]}
    try:
        resp = httpx.get(f"{ITEMS_API}/categories?limit=500", headers=AUTH_HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            categories = data.get("items", []) if isinstance(data, dict) else data
            for c in categories:
                if c.get("name") == name:
                    print(f"  - Category {name} already exists. Skipping.")
                    return c
    except Exception:
        pass

    payload = {"name": name, "description": description}
    try:
        response = httpx.post(f"{ITEMS_API}/categories", json=payload, headers=AUTH_HEADERS)
        if response.status_code == 400 and "already exists" in response.text.lower():
            # Race condition ou seed idempotent : recuperer l existant
            resp2 = httpx.get(f"{ITEMS_API}/categories?limit=500", headers=AUTH_HEADERS)
            if resp2.status_code == 200:
                data2 = resp2.json()
                cats2 = data2.get("items", []) if isinstance(data2, dict) else data2
                for c in cats2:
                    if c.get("name") == name:
                        print(f"  - Category {name} recovered from DB. Skipping.")
                        return c
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


def create_user(first, last, allowed_category_ids=None, suffix=""):
    if allowed_category_ids is None:
        allowed_category_ids = []
    username = f"{first[0].lower()}{last.lower()}{random.randint(10, 9999)}{suffix}"
    email = f"{first.lower()}.{last.lower()}{suffix}@zenika.com"

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


TECH_STACKS = [
    ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes"],
    ["Java", "Spring Boot", "MySQL", "CI/CD", "AWS"],
    ["TypeScript", "Vue.js", "Node.js", "Redis", "GCP"],
    ["Go", "gRPC", "Kafka", "Terraform", "Azure"],
    ["Python", "TensorFlow", "Spark", "BigQuery", "Vertex AI"],
]

ROLES = [
    "Lead Developer", "Architecte Cloud", "Data Engineer",
    "DevOps Engineer", "Tech Lead", "Ingénieur IA", "Consultant Senior",
]

CLIENTS_FAKE = [
    "Renault Digital", "BNP Paribas", "SNCF Connect", "Orange Business",
    "Société Générale", "EDF", "Airbus", "Michelin", "Total Energies",
]


def seed_cv_profiles(user_ids: list) -> int:
    """
    Insere un CVProfile synthetique pour chaque user_id dans la liste.
    Insertion directe en DB (base 'cv') sans passer par le pipeline LLM.
    Idempotent : skip si user_id deja present dans cv_profiles.
    Retourne le nombre de profils inseres.
    """
    if not user_ids:
        return 0

    import psycopg2
    import json as _json

    db_url = get_db_url("cv")
    inserted = 0
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        # Recup les user_ids deja presents (idempotence)
        cur.execute("SELECT DISTINCT user_id FROM cv_profiles")
        existing = {row[0] for row in cur.fetchall()}

        to_insert = [uid for uid in user_ids if uid not in existing]
        print(f"  - {len(existing)} profils CV deja en base, {len(to_insert)} a creer.")

        for uid in to_insert:
            stack = random.choice(TECH_STACKS)
            role = random.choice(ROLES)
            yoe = random.randint(3, 15)
            client1 = random.choice(CLIENTS_FAKE)
            client2 = random.choice(CLIENTS_FAKE)
            summary = (
                f"{role} avec {yoe} ans d'experience. "
                f"Expert en {', '.join(stack[:3])}. "
                f"Missions recentes chez {client1} et {client2}."
            )
            missions = [
                {
                    "title": f"Mission {i + 1}",
                    "client": random.choice(CLIENTS_FAKE),
                    "duration_months": random.randint(6, 24),
                    "skills": random.sample(stack, k=min(3, len(stack))),
                    "description": f"Projet {i + 1} : architecture et developpement avec {stack[0]}.",
                }
                for i in range(random.randint(3, 8))
            ]
            raw = (
                f"CV synthetique perf-test\n"
                f"Role : {role}\n"
                f"Experience : {yoe} ans\n"
                f"Competences : {', '.join(stack)}\n"
                f"Missions : {len(missions)} missions.\n"
            )
            cur.execute(
                """
                INSERT INTO cv_profiles
                    (user_id, source_url, source_tag, extracted_competencies,
                     "current_role", years_of_experience, summary,
                     competencies_keywords, missions, raw_content,
                     is_archived, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (
                    uid,
                    f"perf-test://synthetic/{uid}",
                    "perf-test",
                    _json.dumps([{"name": s, "level": "confirmed"} for s in stack]),
                    role,
                    yoe,
                    summary,
                    stack,
                    _json.dumps(missions),
                    raw,
                    False,
                ),
            )
            inserted += 1

        conn.commit()
        cur.close()
        conn.close()
        print(f"  - {inserted} profils CV synthetiques inseres.")
    except Exception as e:
        print(f"  ❌ Erreur seed CV profiles: {e}")
    return inserted


def erase_data() -> None:
    """Purge toutes les données de test avant un nouveau seed.

    Préserve :
    - Les tables Liquibase (databasechangelog, databasechangeloglock)
    - Les comptes admin@zenika.com et slavayssiere (recrees par main())

    Utilise TRUNCATE ... RESTART IDENTITY CASCADE pour remettre les sequences
    a zero et supprimer les donnees liees par FK en une seule passe.
    """
    import psycopg2

    # (db_name, [tables a truncater dans l'ordre FK-safe])
    # CASCADE gere les dependances, RESTART IDENTITY reset les sequences
    ERASE_PLAN = [
        ("items", ["item_category", "items", "categories"]),
        ("competencies", [
            "user_competency", "competency_evaluations",
            "competency_suggestions", "competencies",
        ]),
        ("cv", ["cv_mission_embeddings", "cv_profiles"]),
        ("missions", ["mission_status_history", "missions"]),
        ("drive", ["drive_sync_state", "drive_folders"]),
        ("prompts", ["prompts"]),
        # users en dernier (FK entrantes depuis competencies.user_competency)
        ("users", ["user_audit_logs", "users"]),
    ]

    print("\n🗑️  Erasing existing test data...")
    for db_name, tables in ERASE_PLAN:
        try:
            conn = psycopg2.connect(get_db_url(db_name))
            cur = conn.cursor()
            tables_sql = ", ".join(tables)
            cur.execute(
                f"TRUNCATE TABLE {tables_sql} RESTART IDENTITY CASCADE;"
            )
            conn.commit()
            cur.close()
            conn.close()
            print(f"  - [{db_name}] {tables_sql} → tronque.")
        except Exception as e:
            print(f"  ❌ Erreur erase [{db_name}]: {e}")

    print("  ✅ Erase termine.")


def main(perf: bool = False) -> None:
    print("🚀 Starting Zenika Seed Data Process...\n")

    erase_data()

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

    user_count = 400 if perf else 12
    item_count = 2000 if perf else 50

    print(f"\n👤 Seeding {user_count} Zenika Users with Permissions...")
    users = []
    for i in range(user_count):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        suffix = f"{i}" if perf else ""
        # Assign 3 to 5 random categories as allowed
        user_allowed_cats = random.sample(category_ids, k=random.randint(3, 5))
        user = create_user(first, last, user_allowed_cats, suffix=suffix)
        if user:
            users.append(user)
        print(f"  - Created user: {user['full_name']} (Allowed Cats: {len(user['allowed_category_ids']) if user else 0})")

    print(f"\n📦 Seeding {item_count} Tagged Items (Respecting Permissions)...")
    for i in range(item_count):
        if not users:
            break
        user = random.choice(users)
        # Randomly assign 1 to 2 categories from the user's ALLOWED ones
        item_categories = random.sample(user['allowed_category_ids'], k=random.randint(1, min(2, len(user['allowed_category_ids']))))
        item = create_item(user['id'], item_categories)
        print(f"  - Created item {i+1}/{item_count}: {item['name']} (assigned to {user['username']})")

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
        "agent_router_api.system_instruction": "agent_router_api/agent_router_api.system_instruction.txt",
        "agent_hr_api.system_instruction": "agent_hr_api/agent_hr_api.system_instruction.txt",
        "agent_ops_api.system_instruction": "agent_ops_api/agent_ops_api.system_instruction.txt",
        "cv_api.extract_cv_info": "cv_api/cv_api.extract_cv_info.txt",
        "cv_api.generate_taxonomy_tree_map": "cv_api/cv_api.generate_taxonomy_tree_map.txt",
        "cv_api.generate_taxonomy_tree_deduplicate": "cv_api/cv_api.generate_taxonomy_tree_deduplicate.txt",
        "cv_api.generate_taxonomy_tree_reduce": "cv_api/cv_api.generate_taxonomy_tree_reduce.txt",
        "cv_api.generate_taxonomy_tree_sweep": "cv_api/cv_api.generate_taxonomy_tree_sweep.txt",
        "missions_api.extract_mission_info": "missions_api/extract_mission_info.txt",
        "missions_api.staffing_heuristics": "missions_api/staffing_heuristics.txt",
        "prompts_api.error_correction": "prompts_api/prompts_api.error_correction.txt"
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

    # Injection de faux CVs pour eviter les 404 lors des tests de perf
    print("\n🎭 Seeding synthetic CV profiles (perf-test, no LLM)...")
    user_ids_for_cv = [u['id'] for u in users if u and u.get('id')]
    seed_cv_profiles(user_ids_for_cv)

    # --- Ecriture du referentiel partage avec locust ---
    print("\n📄 Writing seeded_ids.json for locust referential...")

    # Collecte de tous les item_ids via pagination complete (evite la limite hard de 500)
    item_ids: list[int] = []
    skip = 0
    limit = 100  # max limite acceptee par l'endpoint items_api (le=100)
    while True:
        try:
            resp = httpx.get(
                f"{ITEMS_API}/",
                params={"skip": skip, "limit": limit},
                headers=AUTH_HEADERS,
                timeout=30.0,
            )
            if resp.status_code != 200:
                print(f"  ❌ GET /items/ HTTP {resp.status_code}: {resp.text[:120]}")
                break
            data = resp.json()
            batch = [i["id"] for i in data.get("items", [])]
            item_ids.extend(batch)
            if len(batch) < limit:
                break
            skip += limit
        except Exception as e:
            print(f"  ❌ Erreur collecte item_ids (skip={skip}): {e}")
            break

    # Collecte des mission_ids directement via DB (evite les filtres JWT)
    mission_ids: list[int] = []
    try:
        import psycopg2
        conn = psycopg2.connect(get_db_url("missions"))
        cur = conn.cursor()
        cur.execute("SELECT id FROM missions ORDER BY id LIMIT 5000;")
        mission_ids = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception as e:
        print(f"  ❌ Erreur collecte mission_ids: {e}")

    seeded = {
        "_comment": "Genere par seed_data.py — source de verite pour locustfile.py. Ne pas editer.",
        "_generated_at": datetime.now(timezone.utc).isoformat(),
        "user_ids": [u["id"] for u in users if u and u.get("id")],
        "cv_profile_user_ids": user_ids_for_cv,
        "category_ids": category_ids,
        "item_ids": item_ids,
        "mission_ids": mission_ids,
        "prompt_keys": list(_TEST_DATA.get("prompt_keys", [])),
    }
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_SEEDED_IDS_PATH, "w", encoding="utf-8") as sf:
        json.dump(seeded, sf, indent=2, ensure_ascii=False)
    print(
        f"  - seeded_ids.json ecrit : "
        f"{len(seeded['user_ids'])} users, "
        f"{len(seeded['category_ids'])} categories, "
        f"{len(seeded['item_ids'])} items, "
        f"{len(seeded['mission_ids'])} missions"
    )

    print("\n✨ Done! Zenika Seed process complete.")


if __name__ == "__main__":
    import argparse
    _parser = argparse.ArgumentParser(description="Zenika Seed Data")
    _parser.add_argument("--perf", action="store_true", help="Mode perf : 400 users, 2000 items")
    _args = _parser.parse_args()
    main(perf=_args.perf)
