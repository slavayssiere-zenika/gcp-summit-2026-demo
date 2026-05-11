def render_ui_widgets(resource_uri: str) -> str:
    """
    Indique au frontend quel composant UI utiliser pour afficher les données.
    
    Args:
        resource_uri: L'URI sémantique du composant (ex: ui://empty, ui://consultants, ui://missions).
    
    Returns:
        Un message confirmant la configuration du widget UI.
    """
    return f"Widget UI configuré sur {resource_uri}."
