# Spécifications Globales (Bootstrap)

Ce dossier contient le code Terraform gérant les ressources "fondationnelles" de la plateforme, dites **Singleton**. 

Contrairement aux environnements dynamiques (dev, uat, prd) qui ont un cycle de vie éphémère et répétable, les ressources du Bootstrap sont déployées **une seule fois** de manière globale pour l'ensemble du projet GCP.

## Ressources Déployées

1. **Artifact Registry (`google_artifact_registry_repository`)**
   - Sert de registre Docker unique (`z-gcp-summit-services`) pour stocker toutes les images compilées de nos microservices. Les pipelines CI/CD poussent systématiquement les images vers ce même repository.

2. **Bucket de Stockage Frontend (`google_storage_bucket`)**
   - Hôte exclusif des fichiers statiques compilés de la Single Page Application Vue.js (`z-gcp-summit-frontend`).
   - Le versioning (tar.gz généré par la CI/CD) et l'accès d'hébergement global permettent au Load Balancer des différents environnements d'y router le trafic HTTP(S).

3. **Bucket de State Terraform (`google_storage_bucket`)**
   - Stockage distant (`z-gcp-summit-tf-state`) accueillant l'état Terraform (fichiers `.tfstate`) de nos futurs environnements Platform-Engineering afin de travailler conjointement et éviter la corruption des disques locaux.

4. **Secret Manager (`google_secret_manager_secret`)**
   - Provisionnement des "enveloppes" (ou coquilles vides) de sécurité contenant la clé de signature JWT (`jwt-secret`) ainsi que la clé de l'agent Gemini (`gemini-api-key`). 
   - **Spécificité :** La politique d'organisation (Org Policy Constraints) de Google Cloud forçant le choix strict d'une région, la réplication a été volontairement ajustée en mode `user_managed` ciblant spécifiquement la région autorisée (ex: `europe-west1`), substituant ainsi la réplication globale classique. L'injection des valeurs sensibles doit être réalisée manuellement par l'OPS depuis la console GCP à posteriori.

---
## Mode d'emploi
Ce déploiement ne porte pas de variables d'environnement (`env`) ou de configuration liée au cycle de vie.
```bash
terraform init
terraform apply
```
