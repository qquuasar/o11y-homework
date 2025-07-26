# Магазин кошачьей еды — Observability (o11y)

Полный стек мониторинга, алертов и трассинга для FastAPI‑сервиса «Cat Food Store».

---

## Обзор

- **Сервис**: FastAPI «Cat Food Store» (CRUD товаров и заказов)  
- **БД**: PostgreSQL  
- **Мониторинг**: Prometheus + PostgreSQL‑Exporter  
- **Визуализация**: Grafana (дашборд с p99, RPS, error‑rate, CPU, stock)  
- **Алерты**:  
  - p99 latency > 500 ms → `HighP99Latency`  
  - DB RPS > 100 → `HighPostgresRPS`  
- **Нагрузка**: Locust (UI на 8089)  
- **Трассинг**: Jaeger all‑in‑one (UI на 16686)  

---

## Требования

- Docker & Docker Compose  
- Объём памяти ≳ 4 GB  

---

## Быстрый старт

```bash
git clone <репозиторий>
cd o11y-homework

# Поднять весь стек
docker-compose up --build -d

UI-доступ:

    API/Swagger  → http://localhost:8000/docs

    Prometheus  → http://localhost:9090

    Grafana     → http://localhost:3000 (admin/admin)

    Alertmanager → http://localhost:9093

    Locust      → http://localhost:8089

    Jaeger      → http://localhost:16686

API и Swagger

Вызовы через Swagger UI:

    GET /products

    POST /products

    GET /orders/{id}

    POST /orders

    PUT /orders/{id}/pay

    GET /metrics

Мониторинг
Prometheus

    Конфиг: infra/terraform/prometheus/prometheus.yml

    Scrape targets:

        service:8000/metrics

        postgres-exporter:9187

    Правила: infra/terraform/alertmanager/alerts.yml

Grafana

    Provisioning:

        datasources/prometheus.yaml

        datasources/jaeger.yaml 

        dashboards/cat_food_dashboard.json

    Дашборд «Cat Food Dashboard»:

        p99 latency

        RPS PostgreSQL


Alertmanager → Telegram

    Конфиг: infra/terraform/alertmanager/alertmanager.yml

    Приёмник: Telegram‑бот → public‑канал

    Алерты:

        HighP99Latency (p99 > 0.5 s)

        HighPostgresRPS (DB RPS > 100)

Нагрузочное тестирование (Locust)

    Образ: locust/

    Сценарий: locust/locustfile.py

        Seed-продукты

        GET /products + POST /orders

    UI → http://localhost:8089

    Рекомендации для проверки алертов:

        Users = 100, Spawn rate = 10 → оба алерта срабатывают
        Можно поставить юзеров в 2 раза меньше - тогда будет скорее всего только рпс у бд

Распределённый трассинг (Jaeger)

    Jaeger UI → http://localhost:16686



