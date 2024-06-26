import requests
import pandas as pd
import mysql.connector
from mysql.connector import Error
from frappeclient import FrappeClient

# MySQL database details
mysql_host = "localhost"
mysql_port = "3306"
mysql_user = ""
mysql_password = ""
mysql_database = ""

url = ""
api_key = ""
secret_key = ""

def fetch_all_data(doctype):
    client = FrappeClient(url)
    client.authenticate(api_key, secret_key)

    try:
        items = client.get_list(doctype, limit_start=0, limit_page_length=25000)
        df = pd.DataFrame(items)
        return df
    except Exception as e:
        if hasattr(e, 'response') and e.response.status_code == 400:
            print("Failed to fetch data. Status code:", e.response.status_code)
            print("Response content:", e.response.content)
            return None
        else:
            raise e

def save_to_mysql(df, table_name):
    conn = None
    try:
        conn = mysql.connector.connect(
            host=mysql_host,
            port=mysql_port,
            user=mysql_user,
            password=mysql_password,
            database=mysql_database
        )
        if conn.is_connected():
            cursor = conn.cursor()
            # Creating table if it doesn't exist
            create_table_query = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                {', '.join([f"{col} TEXT" for col in df.columns])}
            )
            """
            cursor.execute(create_table_query)
            conn.commit()

            # Inserting data
            for _, row in df.iterrows():
                insert_query = f"INSERT INTO {table_name} ({', '.join(df.columns)}) VALUES ({', '.join(['%s'] * len(row))})"
                cursor.execute(insert_query, tuple(row))
            conn.commit()
            print(f"Data saved to MySQL database '{mysql_database}' in table '{table_name}'")
    except Error as e:
        print(f"Error: {e}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

# Usage example
if __name__ == "__main__":
    doctype = ""  # Replace with the desired doctype
    table_name = doctype.lower().replace(' ', '_')

    df = fetch_all_data(doctype)
    if df is not None:
        save_to_mysql(df, table_name)
    else:
        print("Failed to fetch data.")
