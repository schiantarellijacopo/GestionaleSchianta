"""Shared MongoDB connection.

Centralizes the Motor client and database handle so that other modules
(auth.py, routes, services) can import `db`/`client` without depending on
server.py — this removes the circular import previously worked around with
late imports.
"""
import os
from motor.motor_asyncio import AsyncIOMotorClient

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]
