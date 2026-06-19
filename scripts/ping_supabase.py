import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Load variables from .env file 
load_dotenv()

# Read connection details from environment. Raises KeyError immediately if either is missing.
url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_ANON_KEY"]

# Create the Supabase client. This does not open a connection yet.
supabase = create_client(url, key)

# Query the keepalive table. The table holds no sensitive data so the anon key is sufficient.
try:
    response = supabase.table("keepalive").select("id").limit(1).execute()
    print(f"Ping successful. Row: {response.data}")
except Exception as e:
    print(f"Ping failed: {e}")
    sys.exit(1)
