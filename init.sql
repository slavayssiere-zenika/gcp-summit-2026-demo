-- init.sql : Initialisation PostgreSQL locale pour le développement
-- Crée les bases de données de chaque microservice + active pgvector

-- Extension pgvector (requise par competencies_api, cv_api)
CREATE EXTENSION IF NOT EXISTS vector;

-- Bases de données des microservices (miroir de db_migrations/docker-entrypoint.sh)
CREATE DATABASE users;
CREATE DATABASE items;
CREATE DATABASE competencies;
CREATE DATABASE cv;
CREATE DATABASE prompts;
CREATE DATABASE drive;
CREATE DATABASE missions;
