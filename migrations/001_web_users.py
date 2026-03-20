"""
Migration 001: Create web_users and link_codes tables
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'vpn_bot.db')

def migrate():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # web_users - for web panel authentication
    c.execute('''CREATE TABLE IF NOT EXISTS web_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP
    )''')
    
    # link_codes - for Telegram linking flow
    c.execute('''CREATE TABLE IF NOT EXISTS link_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        is_used INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()
    print("Migration 001 complete: web_users + link_codes tables created")

if __name__ == '__main__':
    migrate()
