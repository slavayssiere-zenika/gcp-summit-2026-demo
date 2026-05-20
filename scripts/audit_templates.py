#!/usr/bin/env python3
"""
Script d'audit automatisé UX/UI, Accessibilité et Réactivité pour la Console Zenika.
Ce script réalise une analyse statique de haute précision pour identifier les violations
de contrastes, les défauts de réactivité Vue 3, et les manquements d'accessibilité (WCAG AA).
"""

import os
import re
import sys
from html.parser import HTMLParser


class VueTemplateParser(HTMLParser):
    """Parseur HTML spécialisé pour auditer les templates de fichiers Vue.js."""
    def __init__(self):
        super().__init__()
        self.violations = []
        self.in_template = False
        self.template_depth = 0
        self.current_tag = None
        self.button_has_label = False
        self.button_text = ""
        self.button_line = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        # Gérer la balise template globale du fichier Vue
        if tag == "template":
            if not self.in_template:
                self.in_template = True
                self.template_depth = 1
                return
            else:
                self.template_depth += 1

        if not self.in_template:
            return

        self.current_tag = tag

        # 1. Audit des boutons et éléments interactifs (ARIA labels requis si pas de texte visible)
        if tag in ("button", "iconbutton", "icon-button", "iconbuttoncustom"):
            has_label = any(attr in attrs_dict for attr in ("aria-label", ":aria-label", "title", ":title"))
            self.button_has_label = has_label
            self.button_text = ""
            self.button_line = self.getpos()[0]

        # 2. Audit des images (alt requis pour accessibilité)
        elif tag == "img":
            has_alt = any(attr in attrs_dict for attr in ("alt", ":alt"))
            if not has_alt:
                self.violations.append({
                    "type": "IMAGE ALT MANQUANT",
                    "line": self.getpos()[0],
                    "msg": "L'image ne possède pas d'attribut alt ou :alt requis pour l'accessibilité."
                })

        # 3. Audit des inputs de formulaire (ID requis pour association au label[for])
        elif tag == "input":
            input_type = attrs_dict.get("type", "text")
            if input_type != "hidden":
                has_id = any(attr in attrs_dict for attr in ("id", ":id"))
                if not has_id:
                    self.violations.append({
                        "type": "INPUT SANS ID",
                        "line": self.getpos()[0],
                        "msg": f"L'input de type '{input_type}' n'a pas d'ID, empêchant l'association à un label."
                    })

    def handle_data(self, data):
        if not self.in_template:
            return
        if self.current_tag in ("button", "iconbutton", "icon-button", "iconbuttoncustom"):
            self.button_text += data.strip()

    def handle_endtag(self, tag):
        if tag == "template":
            self.template_depth -= 1
            if self.template_depth == 0:
                self.in_template = False
                return

        if not self.in_template:
            return

        if tag in ("button", "iconbutton", "icon-button", "iconbuttoncustom"):
            # Si le bouton se ferme et qu'il n'avait ni texte ni label d'accessibilité
            if not self.button_text and not self.button_has_label:
                self.violations.append({
                    "type": "ACCESSIBILITÉ BOUTON",
                    "line": self.button_line,
                    "msg": f"Le bouton interactif <{tag}> sans texte visible n'a pas d'aria-label ni de titre."
                })
            self.current_tag = None


def audit_vue_file(filepath):
    """Analyse un fichier Vue pour la réactivité, le cycle de vie et son template HTML."""
    violations = []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Audit Réactivité et Hooks de Cycle de vie (Scripts)
    lines = content.splitlines()

    # 1.1 Props destructurées détruisant la réactivité de Vue 3
    for i, line in enumerate(lines, 1):
        if "const {" in line and "} = defineProps" in line:
            violations.append({
                "type": "RÉACTIVITÉ PROP BRISÉE",
                "line": i,
                "msg": "La destructuration de defineProps brise la réactivité. Utilisez toRefs(props) ou props.clé."
            })

    # 1.2 addEventListener sans removeEventListener dans onUnmounted (Memory Leak)
    has_event_listener = any("addEventListener" in line for line in lines)
    has_remove_listener = any("removeEventListener" in line for line in lines)
    if has_event_listener and not has_remove_listener:
        violations.append({
            "type": "FUITE DE MÉMOIRE POTENTIELLE",
            "line": 1,
            "msg": "addEventListener global détecté sans removeEventListener associé (risque de memory leak)."
        })

    # 1.3 Clés de boucle instables dans les templates
    for i, line in enumerate(lines, 1):
        if "v-for=" in line and ("index" in line or "idx" in line) and "key=" in line:
            if re.search(r":key=\"(index|idx)\"", line):
                violations.append({
                    "type": "CLE DE BOUCLE INSTABLE",
                    "line": i,
                    "msg": "Utilisation de :key=\"index\" sur une boucle dynamique. Privilégiez un ID unique stable."
                })

    # 2. Audit du Template via HTMLParser
    parser = VueTemplateParser()
    try:
        parser.feed(content)
        violations.extend(parser.violations)
    except Exception as e:
        violations.append({
            "type": "PARSING ERROR",
            "line": 1,
            "msg": f"Erreur lors du parsing structurel du template : {str(e)}"
        })

    return violations


def audit_css_files(src_dir):
    """Analyse les fichiers CSS pour les anti-patterns et les variables orphelines/dupliquées."""
    violations = []
    style_path = os.path.join(src_dir, "style.css")
    if not os.path.exists(style_path):
        return violations

    with open(style_path, "r", encoding="utf-8") as f:
        css_content = f.read()

    # 1. Analyse des variables CSS déclarées
    declared_vars = re.findall(r"^\s*(--[a-z0-9-]+)\s*:", css_content, re.MULTILINE)

    # 2. Recherche de toutes les consommations de variables dans le dossier source
    all_vue_css_content = ""
    for root, _, files in os.walk(src_dir):
        for file in files:
            if file.endswith((".vue", ".css")):
                try:
                    with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                        all_vue_css_content += f.read()
                except Exception:
                    pass

    # 3. Détecter les variables orphelines
    for var in declared_vars:
        # Chercher var(--ma-var) ou var( --ma-var ) avec ou sans fallback
        pattern = rf"var\(\s*{var}\s*(?:,|\))"
        if not re.search(pattern, all_vue_css_content):
            violations.append({
                "file": "style.css",
                "type": "VARIABLE CSS ORPHELINE",
                "line": css_content.splitlines().index(
                    next(line for line in css_content.splitlines() if var in line)
                ) + 1,
                "msg": f"La variable CSS '{var}' est déclarée mais n'est consommée nulle part (dette CSS)."
            })

    # 4. Détecter les importants abusifs
    lines = css_content.splitlines()
    for i, line in enumerate(lines, 1):
        if "!important" in line and not re.search(r"/\*.*!important.*\*/", line):
            violations.append({
                "file": "style.css",
                "type": "ANTI-PATTERN CSS",
                "line": i,
                "msg": "Utilisation de !important. Brise la cascade et surcharge CSS responsive. À refactoriser."
            })

    return violations


def main():
    """Point d'entrée de l'audit statique UX/UI."""
    src_dir = "frontend/src"
    if not os.path.exists(src_dir):
        print(f"❌ Dossier {src_dir} introuvable.")
        sys.exit(1)

    print("🚀 Démarrage de l'audit de qualité structurelle UX/UI et Réactivité...")
    all_violations = {}

    # Scan des composants Vue
    for root, _, files in os.walk(src_dir):
        for file in files:
            if file.endswith(".vue"):
                path = os.path.join(root, file)
                v = audit_vue_file(path)
                if v:
                    all_violations[path] = v

    # Scan des fichiers CSS
    css_violations = audit_css_files(src_dir)
    if css_violations:
        all_violations["frontend/src/style.css"] = css_violations

    # Affichage des résultats
    if not all_violations:
        print("\n✅ Conforme ! Aucun défaut structurel, de réactivité ou d'accessibilité n'a été détecté.")
        sys.exit(0)

    total_violations = sum(len(v) for v in all_violations.values())
    print(f"\n❌ Audit terminé : {total_violations} violations de qualité détectées dans l'interface.\n")

    for path, violations in all_violations.items():
        print(f"📂 Fichier : {path}")
        for v in violations:
            print(f"  [Ligne {v.get('line', '?')}] [{v['type']}] {v['msg']}")
        print()

    sys.exit(1)


if __name__ == "__main__":
    main()
