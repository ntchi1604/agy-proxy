import os
import platform
import sqlite3
import json
import logging
from pathlib import Path

logger = logging.getLogger("agy_proxy.ide_sync")

def get_vscdb_path() -> Path | None:
    system = platform.system()
    home = Path.home()
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            path = Path(appdata) / "Code" / "User" / "globalStorage" / "state.vscdb"
            if path.exists():
                return path
    elif system == "Darwin":
        path = home / "Library" / "Application Support" / "Code" / "User" / "globalStorage" / "state.vscdb"
        if path.exists():
            return path
    else:
        path = home / ".config" / "Code" / "User" / "globalStorage" / "state.vscdb"
        if path.exists():
            return path
    return None

def sync_ide_accounts(pool) -> int:
    """
    Reads VS Code state.vscdb and imports Google Cloud Code accounts into the AccountPool.
    Returns the number of imported accounts.
    """
    vscdb_path = get_vscdb_path()
    if not vscdb_path:
        logger.debug("VS Code state.vscdb not found.")
        return 0

    imported_count = 0
    try:
        conn = sqlite3.connect(f"file:{vscdb_path}?mode=ro", uri=True)
        cursor = conn.cursor()
        
        # Google Cloud Code accounts are usually stored in 'cloudcode.accounts' or similar.
        # We query any key that might contain Google auth tokens.
        cursor.execute("SELECT key, value FROM ItemTable WHERE key LIKE '%cloudcode%' OR key LIKE '%google%'")
        rows = cursor.fetchall()
        
        for key, value in rows:
            if not value:
                continue
            try:
                data = json.loads(value)
            except Exception:
                continue
            
            # The structure is often a list of accounts or a dict containing accounts
            accounts_to_check = []
            if isinstance(data, list):
                accounts_to_check.extend(data)
            elif isinstance(data, dict):
                # Try common keys
                if "accounts" in data and isinstance(data["accounts"], list):
                    accounts_to_check.extend(data["accounts"])
                else:
                    accounts_to_check.append(data)

            for acc_data in accounts_to_check:
                if not isinstance(acc_data, dict):
                    continue
                
                # Check for token fields
                refresh_token = acc_data.get("refresh_token") or acc_data.get("refreshToken")
                access_token = acc_data.get("access_token") or acc_data.get("accessToken")
                email = acc_data.get("email")
                
                if refresh_token:
                    # Found an account! Check if it's already in the pool
                    exists = False
                    for existing_acc in pool.accounts.values():
                        if existing_acc.auth_method == "consumer" and existing_acc.refresh_token == refresh_token:
                            exists = True
                            break
                        if email and existing_acc.auth_method == "consumer" and existing_acc.email == email:
                            exists = True
                            break
                            
                    if not exists:
                        # Add it to the pool
                        import hashlib
                        seed = email if email else refresh_token
                        acc_id = f"ide_{hashlib.md5(seed.encode('utf-8')).hexdigest()[:8]}"
                        
                        from agy_proxy.auth.base import AccountSession
                        
                        acc = AccountSession(
                            account_id=acc_id,
                            refresh_token=refresh_token,
                            access_token=access_token,
                            email=email,
                            auth_method="consumer",
                            enabled=True,
                            on_token_refreshed=pool.save_accounts
                        )
                        pool.accounts[acc_id] = acc
                        imported_count += 1
                        logger.info("Imported IDE account %s from %s", email or acc_id, key)
                        
        conn.close()
    except Exception as e:
        logger.warning("Failed to sync IDE state from %s: %s", vscdb_path, e)

    if imported_count > 0:
        pool.save_accounts()
        
    return imported_count
