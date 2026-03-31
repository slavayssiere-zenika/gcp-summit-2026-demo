# 🚀 Microservices Monitoring & Tracing Architecture

A modern microservices setup showcasing **FastAPI**, **MCP (Model Context Protocol)**, **Prometheus**, **OpenTelemetry**, and **Jaeger** with a focus on observability and AI Agent capabilities.

---

## 🏗 Project Architecture

This repository contains a 3-tier microservices architecture designed for scalability and high observability:

1.  **Users API (`/users_api`)**:
    *   **Core**: FastAPI service managing user profiles and authentication.
    *   **Data**: PostgreSQL (Database) & Redis (Caching).
    *   **Protocol**: Extends REST with **MCP Server** capabilities to provide contextual user data to AI models.
2.  **Items API (`/items_api`)**:
    *   **Core**: FastAPI service managing resource/item lifecycles.
    *   **Data**: PostgreSQL (Database) & Redis (Caching).
    *   **Protocol**: **MCP Server** for exposing item-related tools to LLMs.
3.  **Web Agent (`/web`)**:
    *   **Core**: A service that acts as an **AI Agent** using **Google Gemini (flash 2.0)**.
    *   **Integration**: Uses **MCP Client** to dynamically browse and interact with both the `users_api` and `items_api`.

---

## 📊 Observability Stack

The system is instrumented for production-grade monitoring:

*   **Prometheus**: Scrapes metrics from all services, including Redis and Postgres exporters.
*   **Grafana Loki & Promtail**: Centralized log streaming collected directly from the Docker socket.
*   **OpenTelemetry**: Automatic instrumentation for FastAPI and SQLAlchemy.
*   **Jaeger / Tempo**: Centralized tracing to visualize request lifecycles across microservices.
*   **Grafana Ready**: All metrics are ready to be visualized (Prometheus endpoints at `/metrics`).

---

## 🚀 Quick Start

### 📋 Prerequisites
- **Docker** & **Docker Compose** installed.
- **Google API Key**: To use the Gemini-powered web agent.

### 🛠 Deployment

1.  **Configure environment variables**:
    ```bash
    export GOOGLE_API_KEY="your-api-key-here"
    ```

2.  **Start the entire stack (Recommended)**:
    ```bash
    docker-compose up --build
    ```

---

## 🔗 Service Endpoints & Dashboards

| Service | Port | Description |
| :--- | :--- | :--- |
| **Web Agent** | `8002` | [http://localhost:8002](http://localhost:8002) - Interaction with the AI Agent |
| **Users API** | `8000` | [http://localhost:8000/docs](http://localhost:8000/docs) - User management Swagger UI |
| **Items API** | `8001` | [http://localhost:8001/docs](http://localhost:8001/docs) - Item management Swagger UI |
| **Prometheus** | `9090` | [http://localhost:9090](http://localhost:9090) - Metrics Dashboard |
| **Grafana** | `3000` | [http://localhost:3000](http://localhost:3000) - Unified Logs, Traces, & Metrics |
| **Jaeger / Tempo** | `16686` | [http://localhost:16686](http://localhost:16686) - Distributed Tracing UI |

---

## 🛠 Features

- **✅ Distributed Tracing**: Every request is traced cross-service via OpenTelemetry OTLP exporter to Jaeger.
- **✅ Real-time Metrics**: Infrastructure and application-level metrics via Prometheus.
- **✅ Intelligent Agent**: The `web` service can "understand" your APIs through the **Model Context Protocol**.
- **✅ Resilient Architecture**: Includes healthchecks and dependency management for reliable startups.

---

## 🏗 Development Notes

### Local Run (without Docker)
Each service can be run locally using `uvicorn main:app --reload` within their respective directories. You will need to provide local instances of Redis and Postgres.
