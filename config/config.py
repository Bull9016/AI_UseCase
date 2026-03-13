import os
import streamlit as st
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

def get_secret(key):
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key)

OPENROUTER_API_KEY = get_secret("OPENROUTER_API_KEY")

SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_KEY = get_secret("SUPABASE_KEY")

CLOUDINARY_URL = get_secret("CLOUDINARY_URL")

WEB_SEARCH_ENABLED = True

DEFAULT_MODEL = "mistralai/mistral-small-3.1-24b-instruct:free"