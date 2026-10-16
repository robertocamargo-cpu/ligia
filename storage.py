import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "pedidos_impressos.db")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pedidos_impressos (
                vda_id TEXT PRIMARY KEY,
                referencia TEXT,
                cliente TEXT,
                data_entrega TEXT,
                arquivo_pdf TEXT,
                impresso_em TIMESTAMP
            )
        """)
        conn.commit()

def pedido_ja_impresso(vda_id: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM pedidos_impressos WHERE vda_id = ?", (str(vda_id),))
        return cursor.fetchone() is not None

def registrar_pedido_impresso(vda_id: str, referencia: str = "", cliente: str = "", data_entrega: str = "", arquivo_pdf: str = ""):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO pedidos_impressos (vda_id, referencia, cliente, data_entrega, arquivo_pdf, impresso_em)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (str(vda_id), referencia, cliente, data_entrega, arquivo_pdf, datetime.now().isoformat()))
        conn.commit()

def listar_ultimos_impressos(limit: int = 10):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT vda_id, referencia, cliente, data_entrega, impresso_em FROM pedidos_impressos ORDER BY impresso_em DESC LIMIT ?", (limit,))
        return cursor.fetchall()

if __name__ == "__main__":
    init_db()
    print("Banco de dados SQLite inicializado:", DB_PATH)
