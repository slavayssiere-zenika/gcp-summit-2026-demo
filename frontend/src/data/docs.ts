export interface ToolDoc {
  name: string
  method: 'GET' | 'POST' | 'PUT' | 'DELETE'
  description: string
  arguments: { name: string; type: string; required?: boolean; description: string }[]
  example: string
}

export interface ServiceDoc {
  id: string
  title: string
  subtitle: string
  description: string
  tools: ToolDoc[]
}

export const docs: Record<string, ServiceDoc> = {
  users: {
    id: 'users',
    title: 'Service des Utilisateurs',
    subtitle: 'Service Users Engine v1.2',
    description: "Ce module MCP orchestre la gestion du cycle de vie des utilisateurs. Il permet l'administration complète des comptes, la recherche avancée et le monitoring de l'état du service.",
    tools: [
      {
        name: 'list_users',
        method: 'GET',
        description: 'Récupère la liste des utilisateurs enregistrés avec pagination haute performance.',
        arguments: [
          { name: 'skip', type: 'int', description: 'Index de départ pour la pagination (défaut: 0)' },
          { name: 'limit', type: 'int', description: 'Nombre maximum de résultats (défaut: 10)' }
        ],
        example: 'list_users(skip=0, limit=20)'
      },
      {
        name: 'get_user',
        method: 'GET',
        description: "Extrait le profil complet d'un utilisateur incluant son état d'activité et ses métadonnées.",
        arguments: [{ name: 'user_id', type: 'int', required: true, description: "L'identifiant interne de l'utilisateur" }],
        example: 'get_user(user_id=42)'
      },
      {
        name: 'create_user',
        method: 'POST',
        description: 'Initialise un nouveau compte utilisateur dans le système.',
        arguments: [
          { name: 'username', type: 'str', required: true, description: 'Identifiant unique de connexion' },
          { name: 'email', type: 'str', required: true, description: 'Adresse de contact valide' },
          { name: 'full_name', type: 'str', description: "Nom complet pour l'affichage" }
        ],
        example: 'create_user(username="j.doe", email="john@zenika.com", full_name="John Doe")'
      }
      // ... (more tools can be added)
    ]
  },
  items: {
    id: 'items',
    title: 'Service des Items',
    subtitle: 'Service Items Engine v1.2',
    description: "Ce module MCP gère le catalogue des objets physiques et numériques. Il maintient les relations de propriété entre les items et les utilisateurs.",
    tools: [
      {
        name: 'list_items',
        method: 'GET',
        description: 'Récupère la liste globale des items avec pagination et gestion du cache.',
        arguments: [
          { name: 'skip', type: 'int', description: 'Index de départ pour la pagination' },
          { name: 'limit', type: 'int', description: 'Volume de données à retourner' }
        ],
        example: 'list_items(skip=0, limit=10)'
      }
    ]
  },
  competencies: {
    id: 'competencies',
    title: 'Service des Compétences',
    subtitle: 'Service Competencies Engine v1.0',
    description: "Ce module MCP gère le catalogue des compétences professionnelles et leurs assignations aux collaborateurs. Il permet de maintenir une cartographie précise des talents au sein de l'organisation.",
    tools: [
      {
        name: 'list_competencies',
        method: 'GET',
        description: 'Récupère la liste exhaustive des compétences du catalogue avec pagination.',
        arguments: [
          { name: 'skip', type: 'int', description: 'Index de départ pour la pagination' },
          { name: 'limit', type: 'int', description: 'Nombre maximum de résultats' }
        ],
        example: 'list_competencies(skip=0, limit=20)'
      },
      {
        name: 'create_competency',
        method: 'POST',
        description: 'Enregistre une nouvelle compétence (skill) dans le référentiel global.',
        arguments: [
          { name: 'name', type: 'str', required: true, description: 'Le libellé de la compétence' },
          { name: 'description', type: 'str', description: 'Une brève explication des acquis' }
        ],
        example: 'create_competency(name="Python", description="Backend Dev")'
      },
      {
        name: 'assign_competency_to_user',
        method: 'POST',
        description: "Établit un lien de maîtrise entre un utilisateur et une compétence.",
        arguments: [
          { name: 'user_id', type: 'int', required: true, description: "L'ID de l'utilisateur" },
          { name: 'competency_id', type: 'int', required: true, description: "L'ID de la compétence" }
        ],
        example: 'assign_competency_to_user(user_id=1, competency_id=5)'
      },
      {
        name: 'list_user_competencies',
        method: 'GET',
        description: 'Extrait le profil complet des compétences pour un utilisateur spécifique.',
        arguments: [{ name: 'user_id', type: 'int', required: true, description: "L'ID du collaborateur" }],
        example: 'list_user_competencies(user_id=1)'
      }
    ]
  }
}
