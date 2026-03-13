import streamlit as st
from supabase import create_client
from config.config import SUPABASE_URL, SUPABASE_KEY


def get_supabase_client():
    """Get or create a Supabase client, restoring session if tokens exist."""
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Restore session from stored tokens (survives Streamlit reruns)
    if "access_token" in st.session_state and st.session_state.access_token:
        try:
            supabase.auth.set_session(
                st.session_state.access_token,
                st.session_state.refresh_token
            )
        except Exception as e:
            print(f"[SESSION RESTORE] Failed: {e}")
            # Tokens expired or invalid — clear them
            st.session_state.access_token = None
            st.session_state.refresh_token = None
            st.session_state.user = None

    return supabase


def _store_session(response):
    """Store auth tokens in session_state so they persist across Streamlit reruns."""
    if response.session:
        st.session_state.access_token = response.session.access_token
        st.session_state.refresh_token = response.session.refresh_token


def login_user(email, password):
    """Sign in an existing user. Returns (user, None) on success or (None, error_msg) on failure."""
    try:
        supabase = get_supabase_client()
        response = supabase.auth.sign_in_with_password(
            {
                "email": email,
                "password": password
            }
        )

        _store_session(response)
        return response.user, None

    except Exception as e:
        error_msg = str(e)
        print(f"[LOGIN ERROR] {error_msg}")

        if "Invalid login credentials" in error_msg:
            return None, "Invalid email or password. Please check and try again."
        elif "Email not confirmed" in error_msg:
            return None, "Please confirm your email before logging in. Check your inbox."
        elif "Invalid API key" in error_msg or "apikey" in error_msg.lower():
            return None, "Server configuration error: Invalid Supabase API key."
        else:
            return None, f"Login error: {error_msg}"


def signup_user(email, password):
    """Register a new user. Returns (user, None) on success or (None, error_msg) on failure."""
    try:
        supabase = get_supabase_client()
        response = supabase.auth.sign_up(
            {
                "email": email,
                "password": password
            }
        )

        user = response.user
        if user and len(user.identities) == 0:
            return None, "An account with this email already exists. Try logging in instead."

        _store_session(response)
        return user, None

    except Exception as e:
        error_msg = str(e)
        print(f"[SIGNUP ERROR] {error_msg}")

        if "already registered" in error_msg.lower():
            return None, "This email is already registered. Try logging in."
        elif "Password should be at least" in error_msg:
            return None, "Password is too short. Use at least 6 characters."
        elif "Invalid API key" in error_msg or "apikey" in error_msg.lower():
            return None, "Server configuration error: Invalid Supabase API key."
        elif "rate limit" in error_msg.lower():
            return None, "Too many attempts. Please wait a minute and try again."
        else:
            return None, f"Sign up error: {error_msg}"


def restore_user_session():
    """Try to restore user session from stored tokens. Call on every app load."""
    if "access_token" not in st.session_state:
        st.session_state.access_token = None
        st.session_state.refresh_token = None

    if st.session_state.access_token and not st.session_state.get("user"):
        try:
            supabase = get_supabase_client()
            session_response = supabase.auth.get_session()
            if session_response and session_response.user:
                st.session_state.user = session_response.user
                # Refresh tokens in case they were rotated
                if session_response.access_token:
                    st.session_state.access_token = session_response.access_token
                if session_response.refresh_token:
                    st.session_state.refresh_token = session_response.refresh_token
                return True
        except Exception as e:
            print(f"[SESSION RESTORE] Could not restore: {e}")
            st.session_state.access_token = None
            st.session_state.refresh_token = None
            st.session_state.user = None
    return False


def logout_user():
    """Clear all auth state."""
    try:
        supabase = get_supabase_client()
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state.user = None
    st.session_state.access_token = None
    st.session_state.refresh_token = None
    st.session_state.messages = []


def update_session_metadata(session_id, schema_context, uploaded_files, file_urls=None):
    """Update session with current data context (schema and file list)."""
    try:
        supabase = get_supabase_client()
        supabase.table("chat_sessions").update({
            "schema_context": schema_context,
            "uploaded_files": list(uploaded_files),
            "file_urls": file_urls or {}
        }).eq("id", session_id).execute()
        return True
    except Exception as e:
        print(f"[UPDATE SESSION ERROR] {e}")
        return False


def get_chat_sessions(user_id):
    """Fetch all chat sessions for the user."""
    try:
        supabase = get_supabase_client()
        response = supabase.table("chat_sessions") \
            .select("*") \
            .eq("user_id", user_id) \
            .order("created_at", desc=True) \
            .execute()
        return response.data
    except Exception as e:
        print(f"[GET SESSIONS ERROR] {e}")
        return []

def create_chat_session(user_id, title="New Chat"):
    """Create a new chat session and return its ID."""
    try:
        supabase = get_supabase_client()
        response = supabase.table("chat_sessions").insert({
            "user_id": user_id,
            "title": title
        }).execute()
        if response.data:
            return response.data[0]["id"]
        return None
    except Exception as e:
        print(f"[CREATE SESSION ERROR] {e}")
        return None

def get_chat_history(session_id):
    """Fetch chats for a specific session."""
    try:
        supabase = get_supabase_client()
        response = supabase.table("chats") \
            .select("*") \
            .eq("session_id", session_id) \
            .order("created_at") \
            .execute()

        return response.data

    except Exception as e:
        print(f"[CHAT HISTORY ERROR] {e}")
        return []


def save_chat(user_id, session_id, user_message, ai_message, sources=None):
    """Save chat to Supabase. Returns (True, None) or (False, error_msg)."""
    try:
        supabase = get_supabase_client()
        
        data = {
            "user_id": user_id,
            "user_message": user_message,
            "ai_message": ai_message,
            "sources": sources # Store sources as a list/json
        }
        if session_id:
            data["session_id"] = session_id
            
        supabase.table("chats").insert(data).execute()
        return True, None

    except Exception as e:
        error_msg = str(e)
        print(f"[SAVE CHAT ERROR] {error_msg}")
        return False, error_msg