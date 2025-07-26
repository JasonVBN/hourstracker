import mysql.connector
from dotenv import load_dotenv
import os
load_dotenv()

config = {
    'host': os.getenv('DB_IP'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASS'),
    'database': 'HoursTracker',
    'port': 3306
}

'''
status options: enum('denied','pending','approved')
'''

def runquery(query: str, params=None) -> list:
    try:
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params)
        print(f"[db/runquery] Executed query: {query} with params: {params}")
        
        result = None
        if cursor.with_rows:
            result = cursor.fetchall()
            print(f"[db/runquery] Retrieved {len(result)} items")
        conn.commit()
        
        return result
    except Exception as e:
        print(f"[db/runquery] Error: {e}")
        return []
    finally:
        cursor.close()
        conn.close()
        print(f"[db/runquery] Connection closed.")

def geteventbyid(event_id: int):
    return runquery("SELECT * FROM events WHERE id = %s", (event_id,))[0]

def addevent(name, hours=0, date=None, desc=None, needproof=False):
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO events"
                   "(name, hours, date, `desc`, needproof) "
                   "VALUES (%s, %s, %s, %s, %s)",
                    (name, hours, date, desc, needproof))
    conn.commit()
    cursor.close()
    conn.close()

def getallevents():
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM events")
    events = cursor.fetchall()

    cursor.close()
    conn.close()

    print(f"[db/getallevents] Events fetched: {len(events)}")
    return events

def updatestatus(id: int, status: str):
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET status = %s WHERE id = %s", (status, id))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"[db/updatestatus] Updated {id} to status {status}")

def getallusers():
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()

    cursor.close()
    conn.close()

    print(f"[db/getallusers] Users fetched: {len(users)}")
    return users

def getuserinfo(email: str):
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    info = cursor.fetchone()
    # if info is None:
    #     print(f"[db/getuserinfo] User is new, adding...")
    #     cursor.execute("INSERT INTO admins (email, name, approved) VALUES (%s, %s, %s)",
    #                    (email, email.split('@')[0], False))
    #     conn.commit()
    #     return {
    #         'email': email,
    #         'name': email.split('@')[0],
    #         'approved': False
    #     }
    cursor.close()
    conn.close()

    print(f"[db/getuserinfo] User fetched: {info}")
    return info

def addnewadmin(email: str, name: str):
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO users (email, name, status, role) 
                    VALUES (%s, %s, %s, 'admin')
                    ON DUPLICATE KEY UPDATE 
                    name=VALUES(name), status='pending', role='admin';""",
                       (email, name, 'pending'))
    conn.commit()
    cursor.close()
    conn.close()

def seetables():
    conn = mysql.connector.connect(**config)
    cursor = conn.cursor()

    cursor.execute("SHOW TABLES;")
    for table in cursor.fetchall():
        print(table)

if __name__ == '__main__':
    seetables()