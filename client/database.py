import sqlite3

def create_user_database(username):
    db_path = f'{username}_torrent_client.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS downloads (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        status TEXT NOT NULL,
        progress REAL NOT NULL,
        magnet TEXT,
        torrent_file TEXT,
        info_hash TEXT NOT NULL,
        download_dir TEXT NOT NULL
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS seeds (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        status TEXT NOT NULL,
        magnet TEXT,
        torrent_file TEXT,
        info_hash TEXT NOT NULL,
        complete_path TEXT NOT NULL
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

def add_download(db_path, name, status, progress, magnet, torrent_file, download_dir, info_hash):
    conn = create_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO downloads (name, status, progress, magnet, torrent_file, download_dir, info_hash) VALUES (?, ?, ?, ?, ?, ?, ?)', (name, status, progress, magnet, torrent_file, download_dir, info_hash))
    conn.commit()
    conn.close()

def update_download(db_path, info_hash, status, progress):
    conn = create_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('UPDATE downloads SET status = ?, progress = ? WHERE info_hash = ?', (status, progress,  info_hash))
    conn.commit()
    conn.close()

def delete_download(db_path, info_hash):
    conn = create_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM downloads WHERE info_hash = ?', (info_hash,))
    conn.commit()
    conn.close()

def get_downloads(db_path):
    conn = create_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM downloads')
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_seed(db_path, name, status, magnet, torrent_file, complete_path, info_hash):
    conn = create_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO seeds (name, status, magnet, torrent_file, complete_path, info_hash) VALUES (?, ?, ?, ?, ?, ?)', (name, status, magnet, torrent_file, complete_path, info_hash))
    conn.commit()
    conn.close()

def get_seeds(db_path):
    conn = create_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM seeds')
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_seed(db_path, info_hash):
    conn = create_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM seeds WHERE info_hash = ?', (info_hash,))
    conn.commit()
    conn.close()

def update_seed(db_path, info_hash, status, torrent_file):
    conn = create_connection(db_path)
    cursor = conn.cursor()
    cursor.execute('UPDATE seeds SET status = ?, torrent_file = ? WHERE info_hash = ?', (status, torrent_file, info_hash))
    conn.commit()
    conn.close()

def get_magnet(db_path, info_hash):
    conn = create_connection(db_path)
    cursor = conn.cursor()
    
    # Tìm magnet link trong bảng downloads
    cursor.execute('SELECT magnet FROM downloads WHERE info_hash = ?', (info_hash,))
    download_magnet = cursor.fetchone()
    
    # Tìm magnet link trong bảng seeds
    cursor.execute('SELECT magnet FROM seeds WHERE info_hash = ?', (info_hash,))
    seed_magnet = cursor.fetchone()
    
    conn.close()
    
    # Kiểm tra và trả về kết quả phù hợp
    if download_magnet and seed_magnet:
        if download_magnet[0] == seed_magnet[0]:
            return download_magnet[0]
        else:
            raise ValueError("Magnet links in downloads and seeds tables do not match.")
    elif download_magnet:
        return download_magnet[0]
    elif seed_magnet:
        return seed_magnet[0]
    else:
        return None