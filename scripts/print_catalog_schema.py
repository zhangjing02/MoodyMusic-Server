# -*- coding: utf-8 -*-
import sqlite3
import os

db_path = r'e:\Workspace\AI-Project\MoodyMusic-Workspace\backend\database\catalog_sync.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("SELECT sql FROM sqlite_master WHERE type='table'")
for row in c.fetchall():
    print(row[0])
    print("-" * 50)
conn.close()
