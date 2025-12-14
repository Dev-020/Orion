import sqlite3
import uuid
import bcrypt
import jwt
import datetime
import os
from typing import Optional, Dict, Any

class AuthManager:
    def __init__(self, db_path: str = "databases/users.db", secret_key: str = "CHANGE_ME_IN_PROD_SECRET"):
        """
        Manages user authentication, registration, and session tokens.
        
        Args:
            db_path (str): Path to the SQLite database file.
            secret_key (str): Secret key for signing JWTs.
        """
        # Ensure data directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        self.db_path = db_path
        self.secret_key = secret_key
        self._init_db()

    def _init_db(self):
        """Initializes the users table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # User Table: UUID (Primary), Username (Unique), Password (Hashed), CreatedAt, TokenVersion
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            token_version INTEGER DEFAULT 0
        )
        ''')
        
        # Try to add column for existing DBs
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass # Column likely exists
            
        conn.commit()
        conn.close()

    def register_user(self, username: str, password: str) -> Dict[str, Any]:
        """
        Registers a new user.
        """
        if not username or not password:
            return {'success': False, 'error': "Username and password are required."}

        # Generate UUID and Hash Password
        user_id = str(uuid.uuid4())
        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (user_id, username, password_hash, token_version) VALUES (?, ?, ?, 0)",
                (user_id, username, hashed_pw)
            )
            conn.commit()
            conn.close()
            print(f"[AuthManager] Registered new user: {username} ({user_id})")
            return {'success': True, 'user_id': user_id, 'username': username}
        except sqlite3.IntegrityError:
            return {'success': False, 'error': "Username already exists."}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def login_user(self, username: str, password: str) -> Dict[str, Any]:
        """Authenticates a user and returns a JWT token."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, password_hash, token_version FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return {'success': False, 'error': "Invalid username or password."}

        # Handle older rows where token_version might be None (if added later)
        user_id, stored_hash, token_version = row
        if token_version is None: token_version = 0
        
        # Verify Password
        if bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8')):
            # Generate JWT with current version
            token = self._generate_token(user_id, username, token_version)
            print(f"[AuthManager] User logged in: {username}")
            return {'success': True, 'token': token, 'user': {'user_id': user_id, 'username': username}}
        else:
            return {'success': False, 'error': "Invalid username or password."}

    def _generate_token(self, user_id: str, username: str, token_version: int) -> str:
        """Generates a JWT token valid for 7 days."""
        payload = {
            'user_id': user_id,
            'username': username,
            'token_version': token_version,
            'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7),
            'iat': datetime.datetime.now(datetime.timezone.utc)
        }
        return jwt.encode(payload, self.secret_key, algorithm='HS256')

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verifies a JWT token. Checks expiration AND revocation (token_version).
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            
            # Check Token Version against DB (Revocation Check)
            user_id = payload.get('user_id')
            token_v = payload.get('token_version', 0)
            
            if not self._check_token_version(user_id, token_v):
                print("[AuthManager] Token revoked (version mismatch).")
                return None
                
            return payload
        except jwt.ExpiredSignatureError:
            print("[AuthManager] Token expired.")
            return None
        except jwt.InvalidTokenError:
            print("[AuthManager] Invalid token.")
            return None

    def _check_token_version(self, user_id: str, token_version: int) -> bool:
        """Helper to check if token version matches DB version."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT token_version FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            conn.close()
            
            if not row: return False
            
            db_version = row[0]
            if db_version is None: db_version = 0
            
            return token_version == db_version
        except Exception:
            return False

    def update_password(self, username: str, new_password: str) -> bool:
        """
        Admin tool to reset a user's password.
        Also increments token_version to invalidate all existing sessions.
        """
        hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get current version to increment
            cursor.execute("SELECT token_version FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            current_version = 0
            if row and row[0] is not None:
                current_version = row[0]
            
            new_version = current_version + 1
            
            cursor.execute(
                "UPDATE users SET password_hash = ?, token_version = ? WHERE username = ?",
                (hashed_pw, new_version, username)
            )
            changes = conn.total_changes
            conn.commit()
            conn.close()
            return changes > 0
        except Exception as e:
            print(f"[AuthManager] Password update failed: {e}")
            return False
