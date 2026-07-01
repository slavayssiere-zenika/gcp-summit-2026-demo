#!/usr/bin/env python3
"""
generate_architecture_report.py — Génération de rapport d'architecture statique + dynamique (Cloud Trace).
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

ROOT = Path(__file__).parent.parent
REPORT_PATH = ROOT / "architecture_report.md"


def check_connection() -> bool:
    """Vérifie si Neo4j accepte les connexions."""
    try:
        with GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as driver:
            driver.verify_connectivity()
            return True
    except Exception:
        return False


def start_neo4j():
    """Démarre le conteneur Neo4j si non actif."""
    print("⏳ Neo4j ne semble pas démarré. Lancement du conteneur...")
    subprocess.run(["docker", "rm", "-f", "neo4j"], capture_output=True)
    cmd = [
        "docker", "run", "-d", "--name", "neo4j",
        "-p", "7474:7474", "-p", "7687:7687",
        "-e", "NEO4J_AUTH=neo4j/password",
        "-e", "NEO4J_PLUGINS=[\"apoc\"]",
        "-e", "NEO4J_dbms_security_procedures_unrestricted=apoc.*",
        "-v", "test-open-code_neo4j_data:/data",
        "neo4j:5"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"❌ Impossible de lancer Neo4j via docker : {res.stderr}")
        sys.exit(1)

    subprocess.run(["docker", "network", "connect", "monitoring_net", "neo4j"], capture_output=True)

    print("⏳ Attente du démarrage de Neo4j...")
    for _ in range(30):
        time.sleep(2)
        if check_connection():
            print("✅ Neo4j est prêt !")
            return
    print("❌ Neo4j n'a pas démarré dans le délai imparti (60s).")
    sys.exit(1)


def run_trace_fetching():
    """Tente de récupérer les traces Cloud Trace depuis GCP."""
    print("📡 Récupération des traces de production (GCP Cloud Trace)...")
    script_path = ROOT / "scripts" / "fetch_cloud_traces.py"
    res = subprocess.run(["python3", str(script_path)], capture_output=True, text=True)
    if res.returncode != 0:
        print("⚠️  Impossible de récupérer les traces Cloud Trace.")
        print(f"   Détail : {res.stderr or res.stdout}")
        print("   L'ingestion se poursuivra en mode statique uniquement.")
    else:
        print("✅ Traces récupérées et mises en cache localement.")


def run_ingestion():
    """Exécute le script d'analyse statique et d'ingestion."""
    print("🚀 Ingestion du graphe d'appels (statique + dynamique) en cours...")
    script_path = ROOT / "scripts" / "build_callgraph.py"
    res = subprocess.run(["python3", str(script_path), "--no-tests"], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"❌ Échec de l'ingestion : {res.stderr or res.stdout}")
        sys.exit(1)
    print("✅ Ingestion terminée avec succès !")


def build_layered_mermaid(relations: list, is_dynamic: bool = False) -> list:
    """Génère le code Mermaid structuré en couches d'architecture avec la charte Zenika."""
    nodes = {}
    for r in relations:
        src, tgt = r["source"], r["target"]
        src_type = r.get("source_type") or (
            "PubSubTopic" if src in ["cv-import-events", "user-events", "data-quality-snapshot"] else "Service"
        )
        tgt_type = r.get("target_type") or (
            "PubSubTopic" if tgt in ["cv-import-events", "user-events", "data-quality-snapshot"] else "Service"
        )
        nodes[src] = src_type
        nodes[tgt] = tgt_type

    # Répartir dans les couches d'architecture
    layers = {
        "gateway": [],
        "agents": [],
        "core": [],
        "mcp": [],
        "pubsub": [],
        "infra": []
    }

    for name, ntype in nodes.items():
        if ntype == "PubSubTopic":
            layers["pubsub"].append((name, ntype))
        elif ntype in ["Database", "GoogleService"] or name in [
            "AlloyDB", "Redis", "BigQuery", "Gemini API", "Google Drive API", "Google OAuth"
        ]:
            layers["infra"].append((name, ntype))
        elif name in ["agent_router_api", "frontend"]:
            layers["gateway"].append((name, ntype))
        elif name in ["agent_hr_api", "agent_ops_api", "agent_missions_api", "agent_commons"]:
            layers["agents"].append((name, ntype))
        elif name in ["analytics_mcp", "monitoring_mcp"]:
            layers["mcp"].append((name, ntype))
        else:
            layers["core"].append((name, ntype))

    lines = ["graph TD"]

    # Écrire les subgraphs de haut en bas (Zenika branding)
    subgraph_titles = [
        ("gateway", "Clients & Passerelle (Gateway)"),
        ("agents", "Agents d'Orchestration IA"),
        ("core", "APIs de Données & Services Core"),
        ("mcp", "MCP Standalone & Observabilité"),
        ("pubsub", "Transport Asynchrone (Pub/Sub)"),
        ("infra", "Stockage de Données & APIs Externes (GCP)")
    ]

    subgraph_styles = {
        "gateway": "style GATEWAY fill:#FFF2F2,stroke:#E60028,stroke-width:2px;",
        "agents": "style AGENTS fill:#F2F2F2,stroke:#3F3F3F,stroke-width:2px;",
        "core": "style CORE fill:#FFF,stroke:#E60028,stroke-width:1.5px;",
        "mcp": "style MCP fill:#F9F9F9,stroke:#7F7F7F,stroke-width:1.5px;",
        "pubsub": "style PUBSUB fill:#FFF9F9,stroke:#E60028,stroke-width:1.5px,stroke-dasharray:5 5;",
        "infra": "style INFRA fill:#F5F7FA,stroke:#2C3E50,stroke-width:2px;"
    }

    active_index = 1
    for key, title in subgraph_titles:
        layer_nodes = sorted(layers[key], key=lambda x: x[0])
        if layer_nodes:
            lines.append(f"    subgraph {key.upper()}[\"{active_index}. {title}\"]")
            active_index += 1
            for node, ntype in layer_nodes:
                node_clean = node.replace("-", "_").replace(" ", "_")
                if key == "pubsub":
                    lines.append(f"        {node_clean}[\"Topic: {node}\"]:::pubsub_style")
                elif ntype == "Database" or node in ["AlloyDB", "Redis", "BigQuery"]:
                    lines.append(f"        {node_clean}[(\"{node}\")]:::db_style")
                elif ntype == "GoogleService" or node in [
                    "Gemini API", "Google Drive API", "Google OAuth"
                ]:
                    lines.append(f"        {node_clean}[\"☁️ {node}\"]:::google_style")
                elif node in ["agent_router_api", "frontend"]:
                    lines.append(f"        {node_clean}[{node}]:::gateway_style")
                elif node.startswith("agent_"):
                    lines.append(f"        {node_clean}[{node}]:::agent")
                elif node.endswith("_mcp"):
                    lines.append(f"        {node_clean}[{node}]:::mcp")
                else:
                    lines.append(f"        {node_clean}[{node}]:::core")
            lines.append("    end")

    # Écrire les relations
    for r in relations:
        src, tgt = r["source"], r["target"]
        src_clean = src.replace("-", "_").replace(" ", "_")
        tgt_clean = tgt.replace("-", "_").replace(" ", "_")

        if is_dynamic:
            rel_label = ""
            if r.get("source_type") == "Service" and r.get("target_type") == "Database":
                if tgt == "AlloyDB":
                    rel_label = "SQL"
                elif tgt == "BigQuery":
                    rel_label = "Analytics"
                else:
                    rel_label = "Cache"
            elif r.get("source_type") == "PubSubTopic" or r.get("target_type") == "PubSubTopic":
                rel_label = "Event"
            elif r.get("target_type") == "GoogleService":
                rel_label = "API"

            label_text = f"|{r['count']} req, {r['avg_latency']:.1f}ms"
            if rel_label:
                label_text += f" ({rel_label})"
            label_text += "|"
            lines.append(f"    {src_clean} -->{label_text} {tgt_clean}")
        else:
            rel_type = r.get("rel_type", "SERVICE_CALLS")
            if rel_type == "PUBLISHES_TO":
                lines.append(f"    {src_clean} -.->|Publie| {tgt_clean}")
            elif rel_type == "SUBSCRIBES_TO":
                ep = r.get("endpoint", "")
                lines.append(f"    {tgt_clean} -.->|Abonné {ep}| {src_clean}")
            elif rel_type == "USES_DB":
                lines.append(f"    {src_clean} -->|Stocke| {tgt_clean}")
            elif rel_type == "CALLS_GOOGLE":
                lines.append(f"    {src_clean} -->|Appelle| {tgt_clean}")
            else:
                lines.append(f"    {src_clean} --> {tgt_clean}")

    # CSS Styles (Charte Zenika)
    lines.append("    classDef gateway_style fill:#E60028,stroke:#333,stroke-width:2px,color:#fff;")
    lines.append("    classDef agent fill:#3F3F3F,stroke:#333,stroke-width:2px,color:#fff;")
    lines.append("    classDef core fill:#fff,stroke:#E60028,stroke-width:1.5px,color:#111;")
    lines.append("    classDef mcp fill:#E0E0E0,stroke:#7F7F7F,stroke-width:1px,color:#111;")
    lines.append(
        "    classDef pubsub_style fill:#FFF2F2,stroke:#E60028,stroke-width:1px,stroke-dasharray: 5 5,color:#111;"
    )
    lines.append("    classDef db_style fill:#fff,stroke:#E60028,stroke-width:2px,color:#111;")
    lines.append("    classDef google_style fill:#2C3E50,stroke:#1A252F,stroke-width:1.5px,color:#fff;")

    # Style des subgraphs actifs
    for key, style_str in subgraph_styles.items():
        if layers[key]:
            lines.append(f"    {style_str}")

    return lines


def build_unified_mermaid(deps: list, tf_deps: list, dyn_deps: list) -> list:
    """Génère le code Mermaid pour la cartographie globale (Big Picture) unifiée."""
    nodes = {}

    # Collecter tous les nœuds et leurs types
    for r in deps + tf_deps:
        src, tgt = r["source"], r["target"]
        src_type = r.get("source_type") or (
            "PubSubTopic" if src in ["cv-import-events", "user-events", "data-quality-snapshot"] else "Service"
        )
        tgt_type = r.get("target_type") or (
            "PubSubTopic" if tgt in ["cv-import-events", "user-events", "data-quality-snapshot"] else "Service"
        )
        nodes[src] = src_type
        nodes[tgt] = tgt_type

    for r in dyn_deps:
        src, tgt = r["source"], r["target"]
        src_type = r.get("source_type") or (
            "PubSubTopic" if src in ["cv-import-events", "user-events", "data-quality-snapshot"] else "Service"
        )
        tgt_type = r.get("target_type") or (
            "PubSubTopic" if tgt in ["cv-import-events", "user-events", "data-quality-snapshot"] else "Service"
        )
        nodes[src] = src_type
        nodes[tgt] = tgt_type

    # Répartir dans les couches d'architecture (même logique)
    layers = {
        "gateway": [],
        "agents": [],
        "core": [],
        "mcp": [],
        "pubsub": [],
        "infra": []
    }

    for name, ntype in nodes.items():
        if ntype == "PubSubTopic":
            layers["pubsub"].append((name, ntype))
        elif ntype in ["Database", "GoogleService"] or name in [
            "AlloyDB", "Redis", "BigQuery", "Gemini API", "Google Drive API", "Google OAuth"
        ]:
            layers["infra"].append((name, ntype))
        elif name in ["agent_router_api", "frontend"]:
            layers["gateway"].append((name, ntype))
        elif name in ["agent_hr_api", "agent_ops_api", "agent_missions_api", "agent_commons"]:
            layers["agents"].append((name, ntype))
        elif name in ["analytics_mcp", "monitoring_mcp"]:
            layers["mcp"].append((name, ntype))
        else:
            layers["core"].append((name, ntype))

    lines = ["graph TD"]

    # Écrire les subgraphs de haut en bas (Zenika branding)
    subgraph_titles = [
        ("gateway", "Clients & Passerelle (Gateway)"),
        ("agents", "Agents d'Orchestration IA"),
        ("core", "APIs de Données & Services Core"),
        ("mcp", "MCP Standalone & Observabilité"),
        ("pubsub", "Transport Asynchrone (Pub/Sub)"),
        ("infra", "Stockage de Données & APIs Externes (GCP)")
    ]

    subgraph_styles = {
        "gateway": "style GATEWAY fill:#FFF2F2,stroke:#E60028,stroke-width:2px;",
        "agents": "style AGENTS fill:#F2F2F2,stroke:#3F3F3F,stroke-width:2px;",
        "core": "style CORE fill:#FFF,stroke:#E60028,stroke-width:1.5px;",
        "mcp": "style MCP fill:#F9F9F9,stroke:#7F7F7F,stroke-width:1.5px;",
        "pubsub": "style PUBSUB fill:#FFF9F9,stroke:#E60028,stroke-width:1.5px,stroke-dasharray:5 5;",
        "infra": "style INFRA fill:#F5F7FA,stroke:#2C3E50,stroke-width:2px;"
    }

    active_index = 1
    for key, title in subgraph_titles:
        layer_nodes = sorted(layers[key], key=lambda x: x[0])
        if layer_nodes:
            lines.append(f"    subgraph {key.upper()}[\"{active_index}. {title}\"]")
            active_index += 1
            for node, ntype in layer_nodes:
                node_clean = node.replace("-", "_").replace(" ", "_")
                if key == "pubsub":
                    lines.append(f"        {node_clean}[\"Topic: {node}\"]:::pubsub_style")
                elif ntype == "Database" or node in ["AlloyDB", "Redis", "BigQuery"]:
                    lines.append(f"        {node_clean}[(\"{node}\")]:::db_style")
                elif ntype == "GoogleService" or node in [
                    "Gemini API", "Google Drive API", "Google OAuth"
                ]:
                    lines.append(f"        {node_clean}[\"☁️ {node}\"]:::google_style")
                elif node in ["agent_router_api", "frontend"]:
                    lines.append(f"        {node_clean}[{node}]:::gateway_style")
                elif node.startswith("agent_"):
                    lines.append(f"        {node_clean}[{node}]:::agent")
                elif node.endswith("_mcp"):
                    lines.append(f"        {node_clean}[{node}]:::mcp")
                else:
                    lines.append(f"        {node_clean}[{node}]:::core")
            lines.append("    end")

    # Dictionnaires pour regrouper les relations
    dyn_map = {(r["source"], r["target"]): r for r in dyn_deps}
    static_map = {(r["source"], r["target"]): r for r in deps}
    tf_map = {(r["source"], r["target"]): r for r in tf_deps}

    all_keys = sorted(list(set(dyn_map.keys()) | set(static_map.keys()) | set(tf_map.keys())))

    # Écrire les relations fusionnées
    for src, tgt in all_keys:
        src_clean = src.replace("-", "_").replace(" ", "_")
        tgt_clean = tgt.replace("-", "_").replace(" ", "_")

        # Priorité 1 : Dynamique (Thick arrow)
        if (src, tgt) in dyn_map:
            r = dyn_map[(src, tgt)]
            rel_label = ""
            if r.get("source_type") == "Service" and r.get("target_type") == "Database":
                if tgt == "AlloyDB":
                    rel_label = "SQL"
                elif tgt == "BigQuery":
                    rel_label = "Analytics"
                else:
                    rel_label = "Cache"
            elif r.get("source_type") == "PubSubTopic" or r.get("target_type") == "PubSubTopic":
                rel_label = "Event"
            elif r.get("target_type") == "GoogleService":
                rel_label = "API"

            label_text = f"|\"{r['count']} req, {r['avg_latency']:.1f}ms"
            if rel_label:
                label_text += f" ({rel_label})"
            # Ajouter une note si présent aussi dans AST / TF
            sources = []
            if (src, tgt) in static_map:
                sources.append("AST")
            if (src, tgt) in tf_map:
                sources.append("TF")
            if sources:
                label_text += f" [{'+'.join(sources)}]"
            label_text += "\"|"
            lines.append(f"    {src_clean} ==>{label_text} {tgt_clean}")

        # Priorité 2 : Statique AST (Standard arrow)
        elif (src, tgt) in static_map:
            r = static_map[(src, tgt)]
            rel_type = r.get("rel_type", "SERVICE_CALLS")
            label = ""
            if rel_type == "PUBLISHES_TO":
                label = "Publie"
            elif rel_type == "SUBSCRIBES_TO":
                ep = r.get("endpoint", "")
                label = f"Abonné {ep}" if ep else "Abonné"
            elif rel_type == "USES_DB":
                label = "Stocke"
            elif rel_type == "CALLS_GOOGLE":
                label = "Appelle"
            else:
                label = "Code"

            # Ajouter une note si présent aussi dans TF
            if (src, tgt) in tf_map:
                label += " [AST+TF]"
            else:
                label += " [AST]"

            lines.append(f"    {src_clean} -->|\"{label}\"| {tgt_clean}")

        # Priorité 3 : Terraform uniquement (Dashed arrow)
        else:
            r = tf_map[(src, tgt)]
            rel_type = r.get("rel_type", "SERVICE_CALLS")
            label = ""
            if rel_type == "PUBLISHES_TO":
                label = "Publie"
            elif rel_type == "SUBSCRIBES_TO":
                ep = r.get("endpoint", "")
                label = f"Abonné {ep}" if ep else "Abonné"
            elif rel_type == "USES_DB":
                label = "Stocke"
            elif rel_type == "CALLS_GOOGLE":
                label = "Appelle"
            else:
                label = "Infra"

            label += " [TF]"
            lines.append(f"    {src_clean} -.->|\"{label}\"| {tgt_clean}")

    # CSS Styles (Charte Zenika)
    lines.append("    classDef gateway_style fill:#E60028,stroke:#333,stroke-width:2px,color:#fff;")
    lines.append("    classDef agent fill:#3F3F3F,stroke:#333,stroke-width:2px,color:#fff;")
    lines.append("    classDef core fill:#fff,stroke:#E60028,stroke-width:1.5px,color:#111;")
    lines.append("    classDef mcp fill:#E0E0E0,stroke:#7F7F7F,stroke-width:1px,color:#111;")
    lines.append(
        "    classDef pubsub_style fill:#FFF2F2,stroke:#E60028,stroke-width:1px,stroke-dasharray: 5 5,color:#111;"
    )
    lines.append("    classDef db_style fill:#fff,stroke:#E60028,stroke-width:2px,color:#111;")
    lines.append("    classDef google_style fill:#2C3E50,stroke:#1A252F,stroke-width:1.5px,color:#fff;")

    # Style des subgraphs actifs
    for key, style_str in subgraph_styles.items():
        if layers[key]:
            lines.append(f"    {style_str}")

    return lines


def run_queries_and_report():
    """Exécute les requêtes Cypher et écrit le rapport markdown."""
    print("📊 Extraction des données et génération du rapport...")
    with GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as driver:
        with driver.session() as session:
            # 1. Stats globales
            q_stats = """
            MATCH (n) RETURN labels(n)[0] AS type, count(n) AS count
            UNION ALL
            MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count
            """
            stats_res = session.run(q_stats)
            stats = {row["type"]: row["count"] for row in stats_res}

            # 2. Dépendances de services et topics Pub/Sub, DB, Google (statiques)
            q_deps = """
            MATCH (n)-[r:SERVICE_CALLS|PUBLISHES_TO|SUBSCRIBES_TO|USES_DB|CALLS_GOOGLE]->(m)
            RETURN n.name AS source, labels(n)[0] AS source_type,
                   m.name AS target, labels(m)[0] AS target_type,
                   type(r) AS rel_type, r.endpoint AS endpoint
            ORDER BY source, target
            """
            deps_res = session.run(q_deps)
            deps = [dict(row) for row in deps_res]

            # 2.b Dépendances d'infrastructure Terraform
            q_tf_deps = """
            MATCH (n)-[r:TERRAFORM_LINK]->(m)
            RETURN n.name AS source, labels(n)[0] AS source_type,
                   m.name AS target, labels(m)[0] AS target_type,
                   r.type AS rel_type, r.endpoint AS endpoint
            ORDER BY source, target
            """
            tf_deps_res = session.run(q_tf_deps)
            tf_deps = [dict(row) for row in tf_deps_res]

            # 3. Dépendances dynamiques (traces de prod)
            q_dyn_deps = """
            MATCH (s1)-[r:DYNAMIC_SERVICE_CALLS|DYNAMIC_DB_CALL|DYNAMIC_GOOGLE_CALL|DYNAMIC_PUBSUB_CALL]->(s2)
            RETURN s1.name AS source, labels(s1)[0] AS source_type,
                   s2.name AS target, labels(s2)[0] AS target_type,
                   r.count AS count, r.avg_latency_ms AS avg_latency
            ORDER BY count DESC
            """
            dyn_deps_res = session.run(q_dyn_deps)
            dyn_deps = [dict(row) for row in dyn_deps_res]

            # 4. Endpoints non protégés (statique)
            q_unsecured = """
            MATCH (e:Function {is_endpoint: true})
            WHERE NOT (e)-[:CALLS*1..3]->(:Function {name: 'verify_jwt'})
            RETURN e.service AS service, e.name AS endpoint, e.filepath AS file, e.line AS line
            ORDER BY service, endpoint
            """
            unsecured_res = session.run(q_unsecured)
            unsecured = [dict(row) for row in unsecured_res]

            # 5. Hotspots statiques (fonctions les plus couplées)
            q_hotspots = """
            MATCH (f:Function)<-[:CALLS]-(caller:Function)
            RETURN f.service AS service, f.name AS function, count(caller) AS incoming_calls
            ORDER BY incoming_calls DESC
            LIMIT 15
            """
            hotspots_res = session.run(q_hotspots)
            hotspots = [dict(row) for row in hotspots_res]

            # 6. Dépendances cycliques (statiques)
            q_cycles = """
            MATCH (s1:Service)-[:SERVICE_CALLS]->(s2:Service)-[:SERVICE_CALLS]->(s1)
            WHERE s1.name < s2.name
            RETURN s1.name AS service_a, s2.name AS service_b
            """
            cycles_res = session.run(q_cycles)
            cycles = [(row["service_a"], row["service_b"]) for row in cycles_res]

            # 7. Code mort statique corrige par la dynamique
            q_dead = """
            MATCH (f:Function)
            WHERE NOT ()-[:CALLS]->(f)
              AND NOT ()-[:DYNAMIC_CALLS]->(f)
              AND NOT f.is_endpoint = true
              AND NOT f.is_mcp_tool = true
            RETURN f.service AS service, f.name AS function, f.filepath AS file, f.line AS line
            ORDER BY service, file
            LIMIT 20
            """
            dead_res = session.run(q_dead)
            dead = [dict(row) for row in dead_res]

            # 8. Endpoints dynamiques les plus lents en prod (Cloud Trace)
            q_slow = """
            MATCH (f1:Function)-[r:DYNAMIC_CALLS]->(f2:Function)
            WHERE f1.is_endpoint = true
            RETURN f1.service AS service, f1.name AS endpoint, r.avg_latency_ms AS avg_latency, r.count AS count
            ORDER BY avg_latency DESC
            LIMIT 10
            """
            slow_res = session.run(q_slow)
            slow_endpoints = [dict(row) for row in slow_res]

            # 9. Flux dynamiques inattendus (non vus statiquement)
            q_unpredicted = """
            MATCH (s1:Service)-[r:DYNAMIC_SERVICE_CALLS]->(s2:Service)
            WHERE NOT (s1)-[:SERVICE_CALLS]->(s2)
            RETURN s1.name AS source, s2.name AS target, r.count AS count
            """
            unpredicted_res = session.run(q_unpredicted)
            unpredicted = [dict(row) for row in unpredicted_res]

            # 10. Flux statiques inactifs (vus statiquement mais 0 appel reel)
            q_inactive = """
            MATCH (s1:Service)-[:SERVICE_CALLS]->(s2:Service)
            WHERE NOT (s1)-[:DYNAMIC_SERVICE_CALLS]->(s2)
            RETURN s1.name AS source, s2.name AS target
            ORDER BY source, target
            """
            inactive_res = session.run(q_inactive)
            inactive_flows = [dict(row) for row in inactive_res]

    # Génération du Markdown
    md = []
    md.append("# 📊 Rapport d'Architecture Applicative (Statique & Dynamique)")
    md.append(f"\n*Généré le {time.strftime('%Y-%m-%d %H:%M:%S')}*")

    md.append("\n## 📈 Statistiques Globales du Graphe")
    md.append("| Élément | Quantité | Description |")
    md.append("| :--- | :--- | :--- |")
    for k, v in sorted(stats.items()):
        desc = ""
        if k == "Service":
            desc = "Nombre de microservices"
        elif k == "Module":
            desc = "Fichiers Python analysés"
        elif k == "Function":
            desc = "Fonctions Python déclarées"
        elif k == "CALLS":
            desc = "Appels de fonctions statiques"
        elif k == "HTTP_CALLS":
            desc = "Appels HTTP statiques inter-services détectés dans le code"
        elif k == "SERVICE_CALLS":
            desc = "Liaisons logiques inter-services (théoriques)"
        elif k == "DYNAMIC_SERVICE_CALLS":
            desc = "Liaisons HTTP réelles détectées dans Cloud Trace (production)"
        elif k == "DYNAMIC_CALLS":
            desc = "Transitions de fonctions réelles mesurées en production"
        elif k == "TERRAFORM_LINK":
            desc = "Liaisons d'infrastructure configurées par Terraform"
        md.append(f"| `{k}` | {v} | {desc} |")

    # --- SECTION BIG PICTURE (CONVOLUTION STATIQUE + DYNAMIQUE + INFRASTRUCTURE) ---
    md.append("\n## 🗺️ Cartographie Globale (Big Picture)")
    md.append(
        "Cette vue unifiée fusionne les liaisons d'infrastructure déclarées par Terraform (pointillés `-.->`), "
        "les appels statiques de l'analyse de code (flèches standard `-->`) et "
        "les flux de requêtes réels capturés par Cloud Trace (flèches épaisses `==>`)."
    )
    md.append("\n```mermaid")
    md.extend(build_unified_mermaid(deps, tf_deps, dyn_deps))
    md.append("```")

    # --- SECTION DYNAMIQUE (GCP CLOUD TRACE) ---
    md.append("\n## 🗺️ Analyse Dynamique des Traces de Production (Cloud Trace)")
    md.append("Cette section présente la topologie réelle des requêtes capturées en production.")

    if dyn_deps:
        md.append("\n### Graphe des Appels Réels (Mermaid)")
        md.append("\n```mermaid")
        md.extend(build_layered_mermaid(dyn_deps, is_dynamic=True))
        md.append("```")

        md.append("\n### Latence et Volume des communications réelles")
        md.append("| Service Source | Service Cible | Volume (1 sem) | Latence Moyenne |")
        md.append("| :--- | :--- | :--- | :--- |")
        for d in dyn_deps:
            md.append(f"| `{d['source']}` | `{d['target']}` | {d['count']} appels | {d['avg_latency']:.2f} ms |")
    else:
        md.append("\n> [!NOTE]")
        md.append("> Aucune trace dynamique n'a pu être importée pour ce rapport.")

    if slow_endpoints:
        md.append("\n### 🐢 Endpoints les plus lents en Production")
        md.append("Basé sur les transitions de fonctions mesurées par Cloud Trace.")
        md.append("\n| Service | Endpoint | Latence Moyenne | Occurrences |")
        md.append("| :--- | :--- | :--- | :--- |")
        for s in slow_endpoints:
            md.append(f"| `{s['service']}` | `{s['endpoint']}` | {s['avg_latency']:.2f} ms | {s['count']} |")

    if unpredicted:
        real_unpredicted = [u for u in unpredicted if u["count"] > 2]
        noise_unpredicted = [u for u in unpredicted if u["count"] <= 2]

        if real_unpredicted:
            md.append("\n### 🕵️ Flux Réels Inattendus (Ombres de l'Architecture)")
            md.append(
                "Ces communications HTTP ont lieu en production mais n'ont pas été détectées par l'analyseur statique."
            )
            md.append("\n> [!WARNING]")
            md.append("> Ces flux contournent généralement la détection statique standard (ex: appels dynamiques MCP).")
            md.append("\n| Service Source | Service Cible | Volume (1 sem) |")
            md.append("| :--- | :--- | :--- |")
            for u in real_unpredicted:
                md.append(f"| `{u['source']}` | `{u['target']}` | {u['count']} appels |")

        if noise_unpredicted:
            md.append("\n### 📡 Bruit de Fond Réseau / Diagnostics")
            md.append(
                "Appels réseau réels très épisodiques, "
                "potentiellement des pings d'observabilité ou des diagnostics de santé."
            )
            md.append("\n| Service Source | Service Cible | Volume (1 sem) |")
            md.append("| :--- | :--- | :--- |")
            for u in noise_unpredicted:
                md.append(f"| `{u['source']}` | `{u['target']}` | {u['count']} appels |")

    # --- SECTION STATIQUE ---
    md.append("\n## 🗺️ Cartographie Statique (Théorique)")
    md.append("\n```mermaid")
    md.extend(build_layered_mermaid(deps, is_dynamic=False))
    md.append("```")

    md.append("\n## 🔄 Dépendances Cycliques (Statiques)")
    if cycles:
        md.append("\n> [!CAUTION]")
        md.append("> Dépendances circulaires détectées entre les services suivants. À corriger en priorité !")
        for sa, sb in cycles:
            md.append(f"- 🔄 **{sa}** <---> **{sb}**")
    else:
        md.append("\n> [!TIP]")
        md.append("> Aucune dépendance cyclique détectée entre les services.")

    md.append("\n## 💤 Flux Statiques Inactifs (Potentiellement obsolètes)")
    md.append(
        "Dépendances déclarées dans le code mais n'ayant enregistré "
        "aucun appel réel dans les traces de production."
    )
    if inactive_flows:
        md.append("\n| Service Source | Service Cible | Statut |")
        md.append("| :--- | :--- | :--- |")
        for f in inactive_flows:
            md.append(f"| `{f['source']}` | `{f['target']}` | 💤 Inactif |")
    else:
        md.append("\n> [!NOTE]")
        md.append("> Toutes les dépendances statiques déclarées ont enregistré au moins un appel en production.")

    md.append("\n## ⚠️ Audit de Sécurité : Endpoints non sécurisés")
    md.append("Endpoints FastAPI sans appel détecté à `verify_jwt` (analyse statique).")
    if unsecured:
        md.append("\n| Service | Endpoint | Fichier | Ligne |")
        md.append("| :--- | :--- | :--- | :--- |")
        for u in unsecured:
            ignored_endpoints = [
                "health", "ready", "root", "get_version", "get_spec", "version",
                "mcp_registry", "agent_card", "login", "logout", "health_agents",
                "health_check", "_health", "metrics", "ping"
            ]
            if u["endpoint"] in ignored_endpoints:
                continue
            rel_file = os.path.relpath(u["file"], ROOT)
            md.append(
                f"| `{u['service']}` | `{u['endpoint']}` | "
                f"[{rel_file}](file://{u['file']}#L{u['line']}) | {u['line']} |"
            )
    else:
        md.append("\n> [!NOTE]")
        md.append("> Aucun endpoint non sécurisé suspect détecté.")

    md.append("\n## 👑 Hotspots Statiques : Fonctions les plus couplées")
    md.append("\n| Service | Fonction | Appels entrants |")
    md.append("| :--- | :--- | :--- |")
    for h in hotspots:
        md.append(f"| `{h['service']}` | `{h['function']}` | {h['incoming_calls']} |")

    md.append("\n## 💤 Code Mort Potentiel (Extrait)")
    if dead:
        md.append("\n| Service | Fonction | Fichier | Ligne |")
        md.append("| :--- | :--- | :--- | :--- |")
        for d in dead:
            rel_file = os.path.relpath(d["file"], ROOT)
            md.append(
                f"| `{d['service']}` | `{d['function']}` | "
                f"[{rel_file}](file://{d['file']}#L{d['line']}) | {d['line']} |"
            )

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    print(f"✅ Rapport enrichi généré dans {REPORT_PATH} !")


def main():
    """Point d'entrée principal."""
    if not check_connection():
        start_neo4j()
    run_trace_fetching()
    run_ingestion()
    run_queries_and_report()


if __name__ == "__main__":
    main()
