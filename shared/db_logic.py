import sqlite3

class DB_Manager:
    def __init__(self, database):
        self.database = database
        self.create_tables()
        try:
            conn = sqlite3.connect(database, timeout=5)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.close()
            print(f"✅ БД доступна: {database}")
        except Exception as e:
            print(f"⚠️ БД НЕ ДОСТУПНА: {e}")

    def create_tables(self):
        conn = sqlite3.connect(self.database, timeout=10)
        with conn:
            # The Ruler
            conn.execute('''CREATE TABLE IF NOT EXISTS user_info (
                                user_id INTEGER PRIMARY KEY,
                                warnings INTEGER DEFAULT 0,
                                reputation INTEGER DEFAULT 0,
                                last_time_reputation REAL DEFAULT 0
                        )''')
            conn.execute('''CREATE TABLE IF NOT EXISTS user_roles (
                                user_id INTEGER,
                                role_id INTEGER,
                                FOREIGN KEY (user_id) REFERENCES user_info(user_id)
                        )''')
            
            # The Economic
            conn.execute('''CREATE TABLE IF NOT EXISTS user_balance (
                                user_id INTEGER PRIMARY KEY,
                                points INTEGER DEFAULT 0,
                                trees INTEGER DEFAULT 0,
                                bugs INTEGER DEFAULT 0,
                                last_claim REAL DEFAULT 0,
                                last_water REAL DEFAULT 0)''') 
            
            # The Fun Bot
            conn.execute('''CREATE TABLE IF NOT EXISTS user_current_aura (
                                user_id INTEGER PRIMARY KEY,
                                current_aura TEXT DEFAULT None
                        )''')
            conn.execute('''CREATE TABLE IF NOT EXISTS user_auras (
                                user_id INTEGER,
                                aura TEXT,
                                FOREIGN KEY (user_id) REFERENCES user_current_aura(user_id)
                        )''')
            conn.commit()
    # The Ruler
    async def get_user_ruler(self, user_id):
        conn = sqlite3.connect(self.database, timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT warnings, reputation FROM user_info WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row is None:
            cursor.execute("INSERT INTO user_info (user_id) VALUES (?)", (user_id,))
            conn.commit()
            row = (0, 0)
        conn.close()
        return {
            "warnings": row[0], 
            "reputation": row[1], 
        }
    
    async def update_user_ruler(self, user_id, warnings, reputation):
        conn = sqlite3.connect(self.database, timeout=10)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE user_info
            SET warnings = ?, reputation = ?
            WHERE user_id = ?
        """, (warnings, reputation, user_id))
        conn.commit()
        conn.close()

    async def get_user_roles_ruler(self, user_id):
        conn = sqlite3.connect(self.database, timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT role_id FROM user_roles WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return []
        return [row[0] for row in rows]
    
    async def update_user_roles_ruler(self, user_id, role_ids):
        conn = sqlite3.connect(self.database, timeout=10)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT 1 FROM user_info WHERE user_id = ?", (user_id,))
            if cursor.fetchone() is None:
                cursor.execute("""
                    INSERT INTO user_info (user_id)
                    VALUES (?)
                """, (user_id,))
            cursor.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
            for role_id in role_ids:
                cursor.execute("""
                    INSERT INTO user_roles (user_id, role_id)
                    VALUES (?, ?)
                """, (user_id, role_id))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError as e:
            conn.close()
            print(f"Integrity error: {e}")
            return False


    # The Economic
    async def get_user_economic(self, user_id):
        conn = None
        try:
            conn = sqlite3.connect(self.database, timeout=5)
            conn.execute("PRAGMA journal_mode=WAL")
            cursor = conn.cursor()
            cursor.execute("SELECT points, trees, bugs, last_claim, last_water FROM user_balance WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row is None:
                cursor.execute("INSERT INTO user_balance (user_id) VALUES (?)", (user_id,))
                conn.commit()
                row = (0, 0, 0, 0.0, 0.0)
            conn.close()
            return {
                "points": row[0], 
                "trees": row[1], 
                "bugs": row[2],
                "last_claim": row[3],
                "last_water": row[4]
            }
        except sqlite3.OperationalError as e:
            print(f"⚠️ Ошибка БД в get_user_economic: {e}")
            return None
        except Exception as e:
            print(f"❌ Другая ошибка: {e}")
            return None
        finally:
            if conn:
                conn.close()
    
    async def update_user_economic(self, user_id, points, trees, bugs, last_claim, last_water):
        conn = sqlite3.connect(self.database, timeout=10)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE user_balance 
            SET points = ?, trees = ?, bugs = ?, last_claim = ?, last_water = ? 
            WHERE user_id = ?
        """, (points, trees, bugs, last_claim, last_water, user_id))
        conn.commit()
        conn.close()

if __name__ == '__main__':
    manager = DB_Manager('fg_db.db')