# locust/locustfile.py

from locust import HttpUser, task, between
import random

class CatFoodUser(HttpUser):
    wait_time = between(1, 2)
    # Гарантируем, что атрибут есть даже до on_start
    product_ids: list[int] = []

    def on_start(self):
        """
        При старте каждого пользователя:
        — Проверяем, сколько сейчас продуктов.
        — Если мало (< DESIRED_PRODUCTS), создаём до DESIRED_PRODUCTS.
        — Всегда заполняем self.product_ids.
        """
        DESIRED_PRODUCTS = 20
        SEED_STOCK = 5000

        # Попытка получить текущий список продуктов
        try:
            resp = self.client.get("/products")
            resp.raise_for_status()
            products = resp.json()
        except Exception as e:
            print("ERROR fetching products in on_start:", e)
            self.product_ids = []
            return

        # Если продуктов меньше DESIRED_PRODUCTS — seed недостающие
        if len(products) < DESIRED_PRODUCTS:
            for i in range(len(products) + 1, DESIRED_PRODUCTS + 1):
                payload = {
                    "name": f"Fish Feast #{i}",
                    "description": "Seeded by Locust",
                    "price": 5.99,
                    "stock": SEED_STOCK
                }
                try:
                    self.client.post("/products", json=payload).raise_for_status()
                except Exception as e:
                    print(f"ERROR creating seed product #{i}:", e)

            # Обновляем список после генерации
            try:
                products = self.client.get("/products").json()
            except:
                products = []

        # Сохраняем все существующие ID
        self.product_ids = [p["id"] for p in products if "id" in p]

    @task(1)
    def list_products(self):
        """GET /products — ничего не ломает."""
        self.client.get("/products")

    @task(3)
    def create_order(self):
        """
        POST /orders — создаём заказ.
        Если product_ids пуст, пропускаем.
        Ловим ошибки и помечаем их в UI.
        """
        if not self.product_ids:
            # Если по каким-то причинам нет ID — пробуем инициализировать заново
            self.on_start()
            if not self.product_ids:
                return

        pid = random.choice(self.product_ids)
        payload = {"items": [{"product_id": pid, "quantity": 1}]}

        with self.client.post("/orders", json=payload, catch_response=True) as r:
            if r.status_code != 201:
                r.failure(f"{r.status_code}: {r.text}")
