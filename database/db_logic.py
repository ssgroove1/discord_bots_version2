import sqlite3

class DB_Manager:
    def __init__(self, database):
        self.database = database
        self.create_tables()

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
            conn.execute("""CREATE TABLE IF NOT EXISTS user_level (
                                user_id INTEGER PRIMARY KEY,
                                xp INTEGER DEFAULT 0,
                                level INTEGER DEFAULT 0,
                                role TEXT DEFAULT 'Нет роли'
                            )
                        """)
            
            # The Economic
            conn.execute('''CREATE TABLE IF NOT EXISTS user_balance (
                                user_id INTEGER PRIMARY KEY,
                                points INTEGER DEFAULT 0,
                                trees INTEGER DEFAULT 0,
                                bugs INTEGER DEFAULT 0,
                                animals INTEGER DEFAULT 0,
                                werewolfs INTEGER DEFAULT 0,
                                last_claim REAL DEFAULT 0,
                                last_water REAL DEFAULT 0,
                                last_collect REAL DEFAULT 0,
                                last_fish REAL DEFAULT 0,
                                last_bonus REAL DEFAULT 0,
                                last_rob REAL DEFAULT 0)''') 
            
            # The Fun Bot
            conn.execute('''CREATE TABLE IF NOT EXISTS user_fun_time (
                                user_id INTEGER PRIMARY KEY,
                                current_aura TEXT DEFAULT None,
                                count_herb INTEGER DEFAULT 0,
                                last_time_herb REAL DEFAULT 0
                        )''')
            conn.execute('''CREATE TABLE IF NOT EXISTS user_auras (
                                user_id INTEGER,
                                aura TEXT,
                                FOREIGN KEY (user_id) REFERENCES user_fun_time(user_id)
                        )''')
            conn.execute('''CREATE TABLE IF NOT EXISTS user_marriages (
                                first_user_id INTEGER,
                                second_user_id INTEGER,
                                created at REAL DEFAULT 0
                        )''')
            conn.commit()
    # The Ruler
    async def get_user_ruler(self, user_id):
        conn = sqlite3.connect(self.database, timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT warnings, reputation, last_time_reputation FROM user_info WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row is None:
            cursor.execute("INSERT INTO user_info (user_id) VALUES (?)", (user_id,))
            conn.commit()
            row = (0, 0, 0.0)
        conn.close()
        return {
            "warnings": row[0], 
            "reputation": row[1],
            "last_time_reputation": row[2],
        }
    
    async def update_user_ruler(self, user_id, warnings, reputation, last_time_reputation):
        conn = sqlite3.connect(self.database, timeout=10)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE user_info
            SET warnings = ?, reputation = ?, last_time_reputation = ?
            WHERE user_id = ?
        """, (warnings, reputation, last_time_reputation, user_id))
        conn.commit()
        conn.close()

    # Roles
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
        
    # Level up
    async def get_user_data(self, user_id: int):
        conn = sqlite3.connect(self.database, timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT xp, level, role FROM user_level WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"xp": row[0], "level": row[1], "role": row[2]}
        return {"xp": 0, "level": 0, "role": "Нет роли"}

    async def update_user_data(self, user_id: int, xp: int, level: int, role: str):
        conn = sqlite3.connect(self.database, timeout=10)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_level (user_id, xp, level, role) 
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET xp = ?, level = ?, role = ?
        """, (user_id, xp, level, role, xp, level, role))
        conn.commit()
        conn.close()

    async def get_xp_needed(self, current_level: int) -> int:
        return 100 + (current_level * 100)

    # The Fun Bot
    async def get_user_funbot(self, user_id):
        conn = None
        try:
            conn = sqlite3.connect(self.database, timeout=5)
            conn.execute("PRAGMA journal_mode=WAL")
            cursor = conn.cursor()
            cursor.execute("SELECT current_aura, count_herb, last_time_herb FROM user_fun_time WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row is None:
                cursor.execute("INSERT INTO user_fun_time (user_id) VALUES (?)", (user_id,))
                conn.commit()
                row = (0, 0, 0.0)
            conn.close()
            return {
                "current_aura": row[0], 
                "count_herb": row[1], 
                "last_time_herb": row[2],
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

    async def update_user_funbot(self, user_id, current_aura, count_herb, last_time_herb):
        conn = sqlite3.connect(self.database, timeout=10)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE user_fun_time
            SET current_aura = ?, count_herb = ?, last_time_herb = ? 
            WHERE user_id = ?
        """, (current_aura, count_herb, last_time_herb, user_id))
        conn.commit()
        conn.close()

    # The Economic
    async def get_user_economic(self, user_id):
        conn = None
        try:
            conn = sqlite3.connect(self.database, timeout=5)
            conn.execute("PRAGMA journal_mode=WAL")
            cursor = conn.cursor()
            cursor.execute("SELECT points, trees, bugs, animals, werewolfs, last_claim, last_water, last_collect, last_fish, last_bonus, last_rob FROM user_balance WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row is None:
                cursor.execute("INSERT INTO user_balance (user_id) VALUES (?)", (user_id,))
                conn.commit()
                row = (0, 0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            conn.close()
            return {
                "points": row[0], 
                "trees": row[1], 
                "bugs": row[2],
                "animals": row[3],
                "werewolfs": row[4],
                "last_claim": row[5],
                "last_water": row[6],
                "last_collect": row[7],
                "last_fish": row[8],
                "last_bonus": row[9],
                "last_rob": row[10]
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
    
    async def update_user_economic(self, user_id, points, trees, bugs, animals, werewolfs, last_claim, last_water, last_collect, last_fish, last_bonus, last_rob):
        conn = sqlite3.connect(self.database, timeout=10)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE user_balance 
            SET points = ?, trees = ?, bugs = ?, animals = ?, werewolfs = ?, last_claim = ?, last_water = ?, last_collect = ?, last_fish = ?, last_bonus = ?, last_rob = ?
            WHERE user_id = ?
        """, (points, trees, bugs, animals, werewolfs, last_claim, last_water, last_collect, last_fish, last_bonus, last_rob, user_id))
        conn.commit()
        conn.close()

    def get_leaderboard(self, limit=10):
        conn = sqlite3.connect(self.database, timeout=10)
        cursor = conn.cursor()
        
        cursor.execute(
            """SELECT user_id, points 
            FROM user_balance 
            WHERE points > 0 
            ORDER BY points DESC 
            LIMIT ?""",
            (limit,)
        )
        
        rows = cursor.fetchall()
        conn.close()
        
        return rows

if __name__ == '__main__':
    manager = DB_Manager('database\\fg_db.db')