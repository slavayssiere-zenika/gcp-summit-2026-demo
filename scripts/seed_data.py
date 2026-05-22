#!/usr/bin/env python3
import json
import random
import string
from datetime import datetime, timezone
import os
import psycopg2

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


def sql_val(val):
    if val is None:
        return "NULL"
    elif isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    elif isinstance(val, (int, float)):
        return str(val)
    elif isinstance(val, datetime):
        return f"'{val.strftime('%Y-%m-%d %H:%M:%S')}'"
    elif isinstance(val, (dict, list)):
        escaped = json.dumps(val).replace("'", "''")
        return f"'{escaped}'"
    else:
        escaped = str(val).replace("'", "''")
        return f"'{escaped}'"


def erase_data() -> None:
    """Purge toutes les données de test avant un nouveau seed."""
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
    print(f"🚀 Starting Fast SQL-based Zenika Seed Data Process (perf={perf})...\n")

    # 1. Purger les anciennes données
    erase_data()

    # Définition des dossiers et chemins de fichiers SQL
    os.makedirs(_DATA_DIR, exist_ok=True)
    sql_files = {
        "users": os.path.join(_DATA_DIR, "users_seed.sql"),
        "items": os.path.join(_DATA_DIR, "items_seed.sql"),
        "competencies": os.path.join(_DATA_DIR, "competencies_seed.sql"),
        "prompts": os.path.join(_DATA_DIR, "prompts_seed.sql"),
        "cv": os.path.join(_DATA_DIR, "cv_seed.sql"),
        "drive": os.path.join(_DATA_DIR, "drive_seed.sql")
    }

    # --- 2. GENERATION SQL USER & PERMISSIONS ---
    print("\n📁 Generating Users & Permissions SQL seed...")
    users_sql_lines = []
    users_sql_lines.append("TRUNCATE TABLE users RESTART IDENTITY CASCADE;")

    # Hash bcrypt stable pré-calculé pour 'admin' et 'slavayssiere' (password: admin)
    admin_hash = "$2b$12$DmcLZx/FfS5ZVVpGVbYOZOM6a27EsafCWBmc26RTxfY5mnn0o/Usi"
    # Hash bcrypt stable pré-calculé pour les utilisateurs standards (password: zenika123)
    user_hash = "$2b$12$XDDf/r.kJV61H29FJv5ayuWQFNrBfcz4A64ic8D7m9HkCnxt/8YC."

    category_mapping = {}
    for idx, (name, desc) in enumerate(CATEGORIES_LIST, start=1):
        category_mapping[name] = idx

    category_ids = list(category_mapping.values())
    ids_str = ",".join(map(str, category_ids))

    # ID 1 : Admin root
    users_sql_lines.append(
        f"INSERT INTO users (id, username, email, first_name, last_name, full_name, "
        f"hashed_password, role, is_active, allowed_category_ids, created_at, is_anonymous) VALUES ("
        f"1, 'admin', 'admin@zenika.com', 'Zenika', 'Admin', 'Zenika Admin', "
        f"{sql_val(admin_hash)}, 'admin', TRUE, {sql_val(ids_str)}, NOW(), FALSE);"
    )

    # ID 2 : Sébastien
    users_sql_lines.append(
        f"INSERT INTO users (id, username, email, first_name, last_name, full_name, "
        f"hashed_password, role, is_active, allowed_category_ids, created_at, is_anonymous) VALUES ("
        f"2, 'slavayssiere', 'sebastien.lavayssiere@zenika.com', 'Sébastien', 'Lavayssière', "
        f"'Sébastien Lavayssière', {sql_val(admin_hash)}, 'admin', TRUE, {sql_val(ids_str)}, NOW(), FALSE);"
    )

    # ID 3 à 7 : Category Managers
    for idx, (name, desc) in enumerate(CATEGORIES_LIST, start=1):
        clean_name = name.lower().replace("é", "e").replace(" ", "")
        uid = 2 + idx
        users_sql_lines.append(
            f"INSERT INTO users (id, username, email, first_name, last_name, full_name, "
            f"hashed_password, role, is_active, allowed_category_ids, created_at, is_anonymous) VALUES ("
            f"{uid}, {sql_val(clean_name)}, {sql_val(f'{clean_name}@zenika.com')}, "
            f"{sql_val(name)}, 'Catégorie', {sql_val(f'Manager {name}')}, "
            f"{sql_val(user_hash)}, 'user', TRUE, {sql_val(str(idx))}, NOW(), FALSE);"
        )

    # ID 8+ : Utilisateurs standards
    user_count = 400 if perf else 12
    seeded_users = []
    start_uid = 3 + len(CATEGORIES_LIST)
    for i in range(user_count):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        suffix = f"{i}" if perf else ""
        username = f"{first[0].lower()}{last.lower()}{random.randint(10, 9999)}{suffix}"
        email = f"{first.lower()}.{last.lower()}{suffix}@zenika.com"
        full_name = f"{first} {last}"

        # Assigne de 3 à 5 catégories aléatoires
        user_allowed_cats = random.sample(category_ids, k=random.randint(3, 5))
        user_allowed_cats_str = ",".join(map(str, user_allowed_cats))
        uid = start_uid + i

        seeded_users.append({
            "id": uid,
            "username": username,
            "email": email,
            "first_name": first,
            "last_name": last,
            "full_name": full_name,
            "allowed_category_ids": user_allowed_cats,
            "allowed_category_ids_str": user_allowed_cats_str
        })

        users_sql_lines.append(
            f"INSERT INTO users (id, username, email, first_name, last_name, full_name, "
            f"hashed_password, role, is_active, allowed_category_ids, created_at, is_anonymous) VALUES ("
            f"{uid}, {sql_val(username)}, {sql_val(email)}, {sql_val(first)}, {sql_val(last)}, "
            f"{sql_val(full_name)}, {sql_val(user_hash)}, 'user', TRUE, "
            f"{sql_val(user_allowed_cats_str)}, NOW(), FALSE);"
        )

    users_sql_lines.append("SELECT setval(pg_get_serial_sequence('users', 'id'), coalesce(max(id), 1)) FROM users;")

    # --- 3. GENERATION SQL ITEMS ---
    print("📁 Generating Items & Categories SQL seed...")
    items_sql_lines = []
    items_sql_lines.append("TRUNCATE TABLE categories RESTART IDENTITY CASCADE;")
    items_sql_lines.append("TRUNCATE TABLE items RESTART IDENTITY CASCADE;")

    # Categories insertion
    for idx, (name, desc) in enumerate(CATEGORIES_LIST, start=1):
        items_sql_lines.append(
            f"INSERT INTO categories (id, name, description, created_at) "
            f"VALUES ({idx}, {sql_val(name)}, {sql_val(desc)}, NOW());"
        )

    # Items insertion (2000 en mode perf, 50 sinon)
    item_count = 2000 if perf else 50
    item_names = [
        "Laptop", "Monitor", "Keyboard", "Mouse", "Desk",
        "Chair", "License", "Server", "Consulting", "Workshop"
    ]
    for idx in range(1, item_count + 1):
        user = random.choice(seeded_users)
        name = f"{random.choice(item_names)} {random_string(4).upper()}"
        desc = f"Standard {name.lower()} for professional use."

        items_sql_lines.append(
            f"INSERT INTO items (id, name, description, user_id, created_at) "
            f"VALUES ({idx}, {sql_val(name)}, {sql_val(desc)}, {user['id']}, NOW());"
        )

        # 1 à 2 catégories choisies parmi celles permises de l'utilisateur
        assigned_cats = random.sample(
            user["allowed_category_ids"],
            k=random.randint(1, min(2, len(user["allowed_category_ids"])))
        )
        for cat_id in assigned_cats:
            items_sql_lines.append(
                f"INSERT INTO item_category (item_id, category_id) "
                f"VALUES ({idx}, {cat_id});"
            )

    items_sql_lines.append(
        "SELECT setval(pg_get_serial_sequence('categories', 'id'), coalesce(max(id), 1)) FROM categories;"
    )
    items_sql_lines.append("SELECT setval(pg_get_serial_sequence('items', 'id'), coalesce(max(id), 1)) FROM items;")

    # --- 4. GENERATION SQL COMPETENCIES ---
    print("📁 Generating Competencies Tree & User Assignments SQL seed...")
    comp_sql_lines = []
    comp_sql_lines.append("TRUNCATE TABLE competencies RESTART IDENTITY CASCADE;")
    comp_sql_lines.append("TRUNCATE TABLE user_competency CASCADE;")

    flat_competencies = []
    next_comp_id = 1

    def flatten_tree(nodes, parent_id=None):
        nonlocal next_comp_id
        if isinstance(nodes, dict):
            for name, content in nodes.items():
                desc = content["description"]
                comp_id = next_comp_id
                next_comp_id += 1
                flat_competencies.append({
                    "id": comp_id,
                    "name": name,
                    "description": desc,
                    "parent_id": parent_id
                })
                if "sub" in content:
                    flatten_tree(content["sub"], comp_id)
        elif isinstance(nodes, list):
            for name, desc in nodes:
                comp_id = next_comp_id
                next_comp_id += 1
                flat_competencies.append({
                    "id": comp_id,
                    "name": name,
                    "description": desc,
                    "parent_id": parent_id
                })

    flatten_tree(COMPETENCIES_ZENIKA_TREE)

    # Insertion des compétences
    for comp in flat_competencies:
        comp_sql_lines.append(
            f"INSERT INTO competencies (id, name, description, parent_id, created_at) "
            f"VALUES ({comp['id']}, {sql_val(comp['name'])}, {sql_val(comp['description'])}, "
            f"{sql_val(comp['parent_id'])}, NOW());"
        )

    # Assignation de 2 à 4 compétences par utilisateur
    comp_ids = [c["id"] for c in flat_competencies]
    for user in seeded_users:
        assigned_comp_ids = random.sample(comp_ids, k=random.randint(2, 4))
        for cid in assigned_comp_ids:
            comp_sql_lines.append(
                f"INSERT INTO user_competency (user_id, competency_id, created_at) "
                f"VALUES ({user['id']}, {cid}, NOW());"
            )

    comp_sql_lines.append(
        "SELECT setval(pg_get_serial_sequence('competencies', 'id'), coalesce(max(id), 1)) FROM competencies;"
    )

    # --- 5. GENERATION SQL PROMPTS ---
    print("📁 Generating Prompts SQL seed...")
    prompts_sql_lines = []
    prompts_sql_lines.append("TRUNCATE TABLE prompts CASCADE;")

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
            prompts_sql_lines.append(
                f"INSERT INTO prompts (key, value, updated_at) "
                f"VALUES ({sql_val(key)}, {sql_val(content)}, NOW());"
            )
        except Exception as e:
            print(f"  ❌ Warning: could not load prompt file '{path}': {e}")

    # --- 6. GENERATION SQL CV PROFILES ---
    print("📁 Generating Synthetic CV Profiles SQL seed...")
    cv_sql_lines = []
    cv_sql_lines.append("TRUNCATE TABLE cv_profiles RESTART IDENTITY CASCADE;")

    user_ids_for_cv = [u["id"] for u in seeded_users]
    for uid in user_ids_for_cv:
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
        extracted = [{"name": s, "level": "confirmed"} for s in stack]

        pg_text_array = f"ARRAY[{', '.join(sql_val(s) for s in stack)}]::text[]"
        cv_sql_lines.append(
            f"INSERT INTO cv_profiles (user_id, source_url, source_tag, extracted_competencies, "
            f"\"current_role\", years_of_experience, summary, competencies_keywords, missions, "
            f"raw_content, is_archived, created_at) VALUES ("
            f"{uid}, {sql_val(f'perf-test://synthetic/{uid}')}, 'perf-test', {sql_val(extracted)}, "
            f"{sql_val(role)}, {yoe}, {sql_val(summary)}, {pg_text_array}, {sql_val(missions)}, "
            f"{sql_val(raw)}, FALSE, NOW());"
        )

    cv_sql_lines.append(
        "SELECT setval(pg_get_serial_sequence('cv_profiles', 'id'), "
        "coalesce(max(id), 1)) FROM cv_profiles;"
    )

    # --- 7. GENERATION SQL DRIVE FOLDERS ---
    print("📁 Generating Drive Mapping SQL seed...")
    drive_sql_lines = []
    drive_sql_lines.append("TRUNCATE TABLE drive_folders RESTART IDENTITY CASCADE;")
    drive_sql_lines.append(
        "INSERT INTO drive_folders (id, google_folder_id, tag, created_at) "
        "VALUES (1, '1WdjkhFc41wYxU3KgirDUH6xYWDSFkDin', 'Niort', NOW());"
    )
    drive_sql_lines.append(
        "SELECT setval(pg_get_serial_sequence('drive_folders', 'id'), "
        "coalesce(max(id), 1)) FROM drive_folders;"
    )

    # --- 8. ECRITURE DES FICHIERS SQL PHYSIQUES ---
    print("\n💾 Writing physical SQL seed files per database...")
    for db_name, lines in [
        ("users", users_sql_lines),
        ("items", items_sql_lines),
        ("competencies", comp_sql_lines),
        ("prompts", prompts_sql_lines),
        ("cv", cv_sql_lines),
        ("drive", drive_sql_lines)
    ]:
        filepath = sql_files[db_name]
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"  - Wrote {filepath} ({len(lines)} lines)")

    # --- 9. EXECUTION DIRECTE EN BD ---
    print("\n⚡ Executing generated SQL seed files directly on PostgreSQL...")
    for db_name, filepath in sql_files.items():
        try:
            conn = psycopg2.connect(get_db_url(db_name))
            cur = conn.cursor()
            with open(filepath, "r", encoding="utf-8") as f:
                sql_content = f.read()
            cur.execute(sql_content)
            conn.commit()
            cur.close()
            conn.close()
            print(f"  - [{db_name}] Successfully seeded directly from SQL file!")
        except Exception as e:
            print(f"  ❌ Error executing seed for [{db_name}] from {filepath}: {e}")

    # --- 10. ECRITURE DU REFERENTIEL PARTAGE AVEC LOCUST ---
    print("\n📄 Writing seeded_ids.json for locust referential...")

    # Collecte rapide et propre des item_ids via SQL
    item_ids = []
    try:
        conn = psycopg2.connect(get_db_url("items"))
        cur = conn.cursor()
        cur.execute("SELECT id FROM items ORDER BY id LIMIT 50000;")
        item_ids = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception as e:
        print(f"  ❌ Erreur collecte SQL item_ids: {e}")

    # Collecte rapide et propre des mission_ids via SQL
    mission_ids = []
    try:
        conn = psycopg2.connect(get_db_url("missions"))
        cur = conn.cursor()
        cur.execute("SELECT id FROM missions ORDER BY id LIMIT 50000;")
        mission_ids = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception as e:
        print(f"  ❌ Erreur collecte SQL mission_ids: {e}")

    seeded = {
        "_comment": "Genere par seed_data.py — source de verite pour locustfile.py. Ne pas editer.",
        "_generated_at": datetime.now(timezone.utc).isoformat(),
        "user_ids": [u["id"] for u in seeded_users],
        "cv_profile_user_ids": user_ids_for_cv,
        "category_ids": category_ids,
        "item_ids": item_ids,
        "mission_ids": mission_ids,
        "prompt_keys": list(_TEST_DATA.get("prompt_keys", [])),
    }

    with open(_SEEDED_IDS_PATH, "w", encoding="utf-8") as sf:
        json.dump(seeded, sf, indent=2, ensure_ascii=False)

    print(
        f"  - seeded_ids.json ecrit : "
        f"{len(seeded['user_ids'])} users, "
        f"{len(seeded['category_ids'])} categories, "
        f"{len(seeded['item_ids'])} items, "
        f"{len(seeded['mission_ids'])} missions"
    )

    print("\n✨ Done! Fast SQL-based Zenika Seed process complete.")


if __name__ == "__main__":
    import argparse
    _parser = argparse.ArgumentParser(description="Zenika Seed Data (SQL-based)")
    _parser.add_argument("--perf", action="store_true", help="Mode perf : 400 users, 2000 items")
    _args = _parser.parse_args()
    main(perf=_args.perf)
