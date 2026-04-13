import asyncpg
import json
from datetime import datetime

async def get_current_rooms():
    try:
        conn = await asyncpg.connect(
            host='localhost',
            port=5432,
            user='postgres',
            password='postgres',
            database='neura_db'
        )
        
        try:
            res = await conn.fetch("SELECT * FROM rooms")
            # Converting thr asyncpg.record objects to dictionaries
            json_data = [
                {key: value.isoformat() if isinstance(value, datetime) else value 
                 for key, value in record.items()}
                for record in res
            ]
            return json.dumps(json_data, ensure_ascii=False)
        finally:
            await conn.close()
    except asyncpg.PostgresError as e:
        print(f"Database error: {e}")
        raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise
