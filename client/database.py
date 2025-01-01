import sqlite3
import os

def create_user_database(username):
    db_path = f'{username}_torrent_client.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS downloads (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        status TEXT NOT NULL,
        progress REAL NOT NULL
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS seeds (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        status TEXT NOT NULL,
        progress REAL NOT NULL
    )
    ''')
    
    conn.commit()
    conn.close()
    return db_path
def create_main_database():
    conn = sqlite3.connect('main_torrent_client.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        db_path TEXT NOT NULL
    )
    ''')
    
    conn.commit()
    conn.close()

def add_user(username, password):
    db_path = create_user_database(username)
    conn = sqlite3.connect('main_torrent_client.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO users (username, password, db_path) VALUES (?, ?, ?)', (username, password, db_path))
    conn.commit()
    conn.close()

def get_user(username, password):
    conn = sqlite3.connect('main_torrent_client.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
    user = cursor.fetchone()
    conn.close()
    return user

def create_connection(db_path):
    conn = sqlite3.connect(db_path)
    return conn

def add_download(db_path, name, status, progress):
    conn = create_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO downloads (name, status, progress) VALUES (?, ?, ?)', (name, status, progress))
    conn.commit()
    conn.close()

def update_download(db_path, name, status, progress):
    conn = create_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('UPDATE downloads SET status = ?, progress = ? WHERE name = ?', (status, progress, name))
    conn.commit()
    conn.close()

def delete_download(db_path, name):
    conn = create_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM downloads WHERE name = ?', (name,))
    conn.commit()
    conn.close()

def get_downloads(db_path):
    conn = create_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM downloads')
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_seed(db_path, name, status, progress):
    conn = create_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO seeds (name, status, progress) VALUES (?, ?, ?)', (name, status, progress))
    conn.commit()
    conn.close()

def update_seed(db_path, name, status, progress):
    conn = create_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('UPDATE seeds SET status = ?, progress = ? WHERE name = ?', (status, progress, name))
    conn.commit()
    conn.close()

def delete_seed(db_path, name):
    conn = create_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM seeds WHERE name = ?', (name,))
    conn.commit()
    conn.close()

def get_seeds(db_path):
    conn = create_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM seeds')
    rows = cursor.fetchall()
    conn.close()
    return rows