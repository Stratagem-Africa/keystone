# Imports
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

supabase = create_client(url, key)

response = supabase.auth.admin.list_users()
print(f"Ping successful. Found {len(response)} user(s).")