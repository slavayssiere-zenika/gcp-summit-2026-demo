# Changelog

## 2026-04-01

### Nouveautés et Améliorations
- Application d'une politique de sécurité *Zero-Trust* : Tous les `APIRouter` (Items, Prompts, Users, Competencies, CV, Agent) sont désormais protégés statiquement par le validateur `verify_jwt`.
- Le token JWT est propagé inter-services et requis pour valider les tests d'intégration.
- Optimisation et maximisation globale de la couverture de test (unitaires et d'intégration) pour l'ensemble des microservices afin de garantir la fiabilité des pipelines.

### Couverture de Code (Code Coverage)

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 929   | 149  | 84%   |
| competencies_api | 727   | 48   | 93%   |
| cv_api           | 614   | 121  | 80%   |
| items_api        | 812   | 61   | 92%   |
| prompts_api      | 394   | 13   | 97%   |
| users_api        | 813   | 50   | 94%   |
