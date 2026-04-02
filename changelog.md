## Mise à jour automatique - 2026-04-02 23:50:00

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 1097  | 85   |  92% |
| competencies_api | 796   | 73   |  91% |
| cv_api           | 804   | 92   |  89% |
| drive_api        | 541   | 296  |  45% |
| items_api        | 880   | 86   |  90% |
| prompts_api      | 462   | 40   |  91% |
| users_api        | 995   | 103  |  90% |

---

## Mise à jour automatique - 2026-04-02 23:46:25

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 1097  | 85   |  92% |
| competencies_api | 796   | 73   |  91% |
| cv_api           | 804   | 92   |  89% |
| items_api        | 880   | 86   |  90% |
| prompts_api      | 462   | 40   |  91% |
| users_api        | 995   | 103  |  90% |

---

## Mise à jour automatique - 2026-04-02 15:08:29

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 996   | 136  |  86% |
| competencies_api | 804   | 76   |  91% |
| cv_api           | 691   | 146  |  79% |
| items_api        | 889   | 89   |  90% |
| prompts_api      | 473   | 39   |  92% |
| users_api        | 900   | 95   |  89% |

---

## Mise à jour automatique - 2026-04-01 19:40:33

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 947   | 132  |  86% |
| competencies_api | 739   | 56   |  92% |
| cv_api           | 626   | 129  |  79% |
| items_api        | 824   | 69   |  92% |
| prompts_api      | 406   | 21   |  95% |
| users_api        | 835   | 68   |  92% |

---

## Mise à jour automatique - 2026-04-01 18:07:12

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 947   | 132  |  86% |
| competencies_api | 739   | 56   |  92% |
| cv_api           | 626   | 129  |  79% |
| items_api        | 824   | 69   |  92% |
| prompts_api      | 406   | 21   |  95% |
| users_api        | 835   | 68   |  92% |

---

## Mise à jour automatique - 2026-04-01 17:38:16

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 947   | 132  |  86% |
| competencies_api | 739   | 56   |  92% |
| cv_api           | 626   | 129  |  79% |
| items_api        | 824   | 69   |  92% |
| prompts_api      | 406   | 21   |  95% |
| users_api        | 835   | 68   |  92% |

---

## Mise à jour automatique - 2026-04-01 12:09:27

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 930   | 117  |  87% |
| competencies_api | 727   | 48   |  93% |
| cv_api           | 614   | 121  |  80% |
| items_api        | 812   | 61   |  92% |
| prompts_api      | 394   | 13   |  97% |
| users_api        | 813   | 50   |  94% |

---

## Mise à jour automatique - 2026-04-01 12:02:57

### Couverture de Code

| Microservice     | Stmts | Miss | Cover |
|------------------|-------|------|-------|
| agent_api        | 929   | 149  |  84% |
| competencies_api | 727   | 48   |  93% |
| cv_api           | 614   | 121  |  80% |
| items_api        | 812   | 61   |  92% |
| prompts_api      | 394   | 13   |  97% |
| users_api        | 813   | 50   |  94% |

---

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
