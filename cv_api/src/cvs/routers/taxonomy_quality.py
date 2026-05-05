def evaluate_taxonomy_quality(res_tree: dict, missing_competencies: list, sweep_assignments: list, merges: list) -> dict:
    """Évalue la qualité de la taxonomie générée et retourne un rapport."""
    report = {
        "passed": True,
        "metrics": {},
        "issues": []
    }
    
    # 1. Taux de concentration des Piliers
    total_nodes = 0
    pillar_counts = {}
    
    def count_nodes(node):
        count = 0
        if isinstance(node, dict):
            for k, v in node.items():
                count += 1 + count_nodes(v)
        elif isinstance(node, list):
            for item in node:
                count += 1 + count_nodes(item)
        return count

    for pillar_name, content in res_tree.items():
        pc = count_nodes(content)
        pillar_counts[pillar_name] = pc
        total_nodes += pc
        
    if total_nodes > 0:
        max_pillar = max(pillar_counts.items(), key=lambda x: x[1])
        concentration_pct = (max_pillar[1] / total_nodes) * 100
        report["metrics"]["max_pillar_concentration"] = {
            "name": max_pillar[0],
            "pct": round(concentration_pct, 1)
        }
        
        if concentration_pct > 35.0:
            report["passed"] = False
            report["issues"].append(f"Le pilier '{max_pillar[0]}' concentre trop de compétences ({round(concentration_pct, 1)}% > 35%). Risque d'effet 'Fourre-tout'.")
    
    # 2. Sweep Success Rate
    total_missing = len(missing_competencies)
    if total_missing > 0:
        assigned = len(sweep_assignments) + len(merges)
        success_rate = min(100.0, (assigned / total_missing) * 100)
        report["metrics"]["sweep_success_rate"] = round(success_rate, 1)
        
        if success_rate < 80.0:
            # We don't fail, but we warn
            report["issues"].append(f"Taux de rattrapage (Sweep) faible : {round(success_rate, 1)}% (moins de 80%). Trop d'orphelines.")
    else:
        report["metrics"]["sweep_success_rate"] = 100.0
        
    return report
