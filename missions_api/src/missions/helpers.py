def extract_mid_parents(nodes: list[dict]) -> list[str]:
    parents: list[str] = []
    for n in nodes:
        subs: list = n.get("sub_competencies") or []
        if subs:
            has_leaf_child = any(not s.get("sub_competencies") for s in subs)
            if has_leaf_child and n.get("parent_id") is not None and n.get("name"):
                parents.append(n["name"])
            parents.extend(extract_mid_parents(subs))
    return parents

def _collect_leaves(nodes: list[dict], acc: list[str]) -> None:
    for n in nodes:
        subs: list = n.get("sub_competencies") or []
        if not subs:
            name: str | None = n.get("name")
            if name:
                acc.append(name)
        else:
            _collect_leaves(subs, acc)

def extract_leaf_names(nodes: list[dict], max_leaves: int = 300) -> list[str]:
    acc: list[str] = []
    _collect_leaves(nodes, acc)
    return acc[:max_leaves]

def _collect_all_known_names(nodes: list[dict]) -> set[str]:
    """Retourne les noms canoniques ET tous les aliases de TOUTES les compétences (feuilles et parents).

    Utilisé pour le filtre pré-suggestion (Axe 4) : évite de soumettre
    des suggestions pour des compétences (comme 'DevOps') qui existent déjà
    comme nœuds parents ou avec des aliases dans la taxonomie.
    """
    known: set[str] = set()

    def _traverse(n_list: list[dict]) -> None:
        for n in n_list:
            name: str | None = n.get("name")
            if name:
                known.add(name.lower())
            aliases_str: str = n.get("aliases") or ""
            for alias in aliases_str.split(","):
                a = alias.strip()
                if a:
                    known.add(a.lower())
            
            subs: list = n.get("sub_competencies") or []
            if subs:
                _traverse(subs)

    _traverse(nodes)
    return known

def build_taxonomy_context(nodes: list[dict], max_leaves: int = 300) -> tuple[str, int, int]:
    import json
    parent_categories = extract_mid_parents(nodes)
    leaf_names = extract_leaf_names(nodes, max_leaves=max_leaves)
    context = (
        "\n\nHere is the official taxonomy for this company's competencies."
        f"\n\n1. PARENT DOMAINS — use these as the 'parent' field for each extracted competency:\n{json.dumps(parent_categories)}"
        f"\n\n2. EXISTING LEAF COMPETENCIES — if a skill matches one of these exactly (or is an alias/abbreviation), "
        f"use this EXACT name instead of creating a variant "
        f"(e.g. map 'K8s' → 'Kubernetes', 'GCP' → 'Google Cloud Platform'):\n{json.dumps(leaf_names)}"
    )
    return context, len(parent_categories), len(leaf_names)

def find_domains_for_skills(skills: list[str], nodes: list[dict]) -> list[str]:
    if not skills or not nodes:
        return []
    domains = set()
    skills_lower = {s.lower() for s in skills}
    def _search(current_nodes: list[dict], current_domain: str | None = None) -> None:
        for node in current_nodes:
            node_name = node.get("name", "")
            node_domain = current_domain
            has_children = bool(node.get("sub_competencies"))
            if has_children and not current_domain:
                node_domain = node_name
            if node_name.lower() in skills_lower:
                if node_domain:
                    domains.add(node_domain)
            aliases = node.get("aliases")
            if aliases:
                for alias in aliases.split(","):
                    if alias.strip().lower() in skills_lower:
                        if node_domain:
                            domains.add(node_domain)
                        break
            if has_children:
                _search(node.get("sub_competencies", []), node_domain)
    _search(nodes)
    return sorted(list(domains))
