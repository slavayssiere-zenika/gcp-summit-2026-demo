from src.missions.helpers import (
    extract_mid_parents,
    extract_leaf_names,
    _collect_all_known_names,
    build_taxonomy_context,
    find_domains_for_skills
)

def test_extract_mid_parents():
    nodes = [
        {"name": "Domain1", "parent_id": None, "sub_competencies": [
            {"name": "MidParent", "parent_id": 1, "sub_competencies": [
                {"name": "Leaf1", "parent_id": 2, "sub_competencies": []}
            ]}
        ]}
    ]
    parents = extract_mid_parents(nodes)
    assert parents == ["MidParent"]

def test_extract_leaf_names():
    nodes = [
        {"name": "Domain1", "parent_id": None, "sub_competencies": [
            {"name": "Sub1", "parent_id": 1, "sub_competencies": []},
            {"name": "Sub2", "parent_id": 1, "sub_competencies": []}
        ]}
    ]
    leaves = extract_leaf_names(nodes)
    assert set(leaves) == {"Sub1", "Sub2"}

def test_collect_all_known_names():
    nodes = [
        {"name": "Domain1", "aliases": "D1, dom1", "sub_competencies": [
            {"name": "Sub1", "aliases": "S1"},
            {"name": "Sub2", "aliases": ""}
        ]}
    ]
    known = _collect_all_known_names(nodes)
    assert known == {"domain1", "d1", "dom1", "sub1", "s1", "sub2"}

def test_build_taxonomy_context():
    nodes = [
        {"name": "Domain1", "parent_id": None, "sub_competencies": [
            {"name": "MidParent", "parent_id": 1, "sub_competencies": [
                {"name": "Leaf1", "parent_id": 2, "sub_competencies": []}
            ]}
        ]}
    ]
    context, p_len, l_len = build_taxonomy_context(nodes)
    assert "PARENTS" in context or "PARENT" in context
    assert p_len == 1
    assert l_len == 1

def test_find_domains_for_skills():
    nodes = [
        {"name": "Domain1", "parent_id": None, "sub_competencies": [
            {"name": "Sub1", "aliases": "S1"},
            {"name": "Sub2"}
        ]}
    ]
    skills = ["Sub1", "s1", "unknown"]
    domains = find_domains_for_skills(skills, nodes)
    assert domains == ["Domain1"]
    
    assert find_domains_for_skills([], []) == []
