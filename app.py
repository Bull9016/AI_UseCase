import streamlit as st

from models.llm import generate_response
from utils.rag import VectorStore
from utils.web_search import search_web
from utils.document_processor import process_uploaded_file
from utils.supabase_db import (
    login_user, signup_user, get_chat_history,
    save_chat, restore_user_session, logout_user,
    get_chat_sessions, create_chat_session
)
from utils.cloudinary_storage import upload_document_to_cloudinary


st.set_page_config(
    page_title="Data Analyst AI Assistant",
    page_icon="📊",
    layout="wide"
)

# --- INIT SESSION STATES ---
if "user" not in st.session_state:
    st.session_state.user = None

if "show_login" not in st.session_state:
    st.session_state.show_login = False

if "vector_store" not in st.session_state:
    st.session_state.vector_store = VectorStore()

if "messages" not in st.session_state:
    st.session_state.messages = []

if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = set()

if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None

# --- RESTORE SESSION ON RELOAD ---
# This checks if we have stored auth tokens and restores the user session
if not st.session_state.user:
    restored = restore_user_session()
    if restored and st.session_state.user:
        pass # Default to a new chat upon reload 

st.title("📊 Data Analyst AI Assistant")

# --- SIDEBAR UI ---
with st.sidebar:
    if st.button("➕ New Chat", use_container_width=True):
        st.session_state.current_session_id = None
        st.session_state.messages = []
        st.session_state.vector_store = VectorStore()
        st.session_state.uploaded_files = set()
        st.rerun()

    st.markdown("### 💬 Your Chats")

    if not st.session_state.user:
        st.info("Login to save data & sync sessions.")
    else:
        sessions = get_chat_sessions(st.session_state.user.id)
        if sessions:
            for s in sessions:
                # Add a distinct visual look for active session
                btn_label = f"📌 {s['title']}" if st.session_state.current_session_id == s['id'] else s['title']
                if st.button(btn_label, key=s["id"], use_container_width=True):
                    st.session_state.current_session_id = s["id"]
                    history = get_chat_history(s["id"])
                    st.session_state.messages = []
                    st.session_state.vector_store = VectorStore()  # Knowledge resets per session switch
                    st.session_state.uploaded_files = set()
                    for chat in history:
                        st.session_state.messages.append({"role": "user", "content": chat["user_message"]})
                        st.session_state.messages.append({"role": "assistant", "content": chat["ai_message"]})
                    st.rerun()
        else:
            st.caption("No recent chats.")

    st.markdown("---")

    if not st.session_state.user:
        if st.button("Log In / Sign Up", use_container_width=True):
            st.session_state.show_login = True
            st.rerun()
    else:
        st.markdown(f"👤 **{st.session_state.user.email}**")
        if st.button("Log Out", use_container_width=True):
            logout_user()
            st.rerun()

# --- LOGIN PAGE LOGIC ---
if st.session_state.show_login and not st.session_state.user:
    st.markdown("## Login or Sign Up")

    auth_mode = st.radio("Choose Action", ["Login", "Sign Up"], horizontal=True, label_visibility="collapsed")

    email = st.text_input("Email", key="login_email")
    password = st.text_input("Password", type="password", key="login_password")

    col_auth, col_cancel = st.columns([1, 1])
    with col_auth:
        if st.button(auth_mode, use_container_width=True):
            if not email or not password:
                st.error("Please enter both email and password.")
            elif auth_mode == "Login":
                user, error = login_user(email, password)
                if user:
                    st.session_state.user = user
                    st.session_state.show_login = False

                    st.session_state.current_session_id = None
                    st.session_state.messages = []
                    st.rerun()
                else:
                    st.error(error or "Login failed.")
            else:  # Sign Up
                user, error = signup_user(email, password)
                if user:
                    st.session_state.user = user
                    st.session_state.show_login = False
                    st.session_state.messages = []
                    st.success("Account created successfully!")
                    st.rerun()
                else:
                    st.error(error or "Sign up failed.")

    with col_cancel:
        if st.button("Cancel", use_container_width=True):
            st.session_state.show_login = False
            st.rerun()

    st.stop()

# --- MAIN CHAT UI CONTROLS ---
col_model, col_mode = st.columns([3, 1])
with col_model:
    model = st.selectbox(
        "Choose Model",
        [
            "mistralai/mistral-small-3.1-24b-instruct:free",
            "google/gemma-3-27b-it:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "qwen/qwen3-coder:free"
        ],
        label_visibility="collapsed"
    )
with col_mode:
    mode = st.selectbox("Response Mode", ["Concise", "Detailed"], label_visibility="collapsed")

st.markdown("---")

# DISPLAY CHAT HISTORY

for msg in st.session_state.messages:

    st.chat_message(msg["role"]).write(msg["content"])


# ATTACHMENT POPOVER (Positioned right above chat input)
with st.container():
    col_attach, col_info = st.columns([1, 4])
    with col_attach:
        with st.popover("📎 Attach"):
            uploaded_file = st.file_uploader(
                "Knowledge Base Document",
                type=["txt", "csv", "pdf"],
                key="doc_uploader",
                label_visibility="collapsed"
            )
            if uploaded_file and uploaded_file.name not in st.session_state.uploaded_files:
                with st.spinner(f"Uploading {uploaded_file.name}..."):
                    try:
                        # 1. Cloudinary
                        c_url, _ = upload_document_to_cloudinary(uploaded_file.getvalue(), uploaded_file.name)
                        st.toast(f"Saved to Cloudinary!")
                        
                        # 2. Local Vector Store (RAG)
                        uploaded_file.seek(0)
                        chunks, error = process_uploaded_file(uploaded_file)
                        if not error:
                            for chunk in chunks:
                                st.session_state.vector_store.add_document(chunk, metadata={"source": uploaded_file.name})
                            st.session_state.uploaded_files.add(uploaded_file.name)
                            st.success(f"✅ Indexed for chat context!")
                        else:
                            st.error(error)
                    except Exception as e:
                        st.error(f"Upload error: {e}")
                        
    with col_info:
        doc_count = len(st.session_state.vector_store.documents)
        if doc_count > 0:
            st.caption(f"📚 {doc_count} context chunks active")


# CHAT INPUT

user_input = st.chat_input("Ask your analytics question...")


if user_input:

    # Auto-create session if None
    if st.session_state.user and not st.session_state.current_session_id:
        title = user_input[:30] + "..." if len(user_input) > 30 else user_input
        new_sid = create_chat_session(st.session_state.user.id, title=title)
        st.session_state.current_session_id = new_sid

    st.session_state.messages.append(
        {"role": "user", "content": user_input}
    )

    st.chat_message("user").write(user_input)

    rag_results = st.session_state.vector_store.search(user_input)

    # Format context and track used sources
    used_sources = set()
    rag_context_parts = []
    for res in rag_results:
        source_name = res["metadata"].get("source", "Unknown Document")
        used_sources.add(source_name)
        rag_context_parts.append(f"[Source: {source_name}]\n{res['text']}")
        
    rag_context = "\n\n".join(rag_context_parts)

    web_results = search_web(user_input)
    web_context = "\n".join(web_results)

    context = f"{rag_context}\n\n{web_context}"


    if mode == "Concise":

        system_prompt = (
            "You are a senior Data Analyst AI Assistant. "
            "Give short, precise answers focused on data insights, SQL queries, "
            "metrics, and actionable analytics. Use bullet points where helpful. "
            "If the user provides document context, prioritize that data."
        )

    else:

        system_prompt = (
            "You are a senior Data Analyst AI Assistant. "
            "Provide detailed, in-depth analytical responses. Explain your reasoning step-by-step, "
            "include SQL query logic where relevant, describe statistical methods, "
            "suggest visualizations, and provide actionable business insights. "
            "If the user provides document context, analyze it thoroughly."
        )

    messages = [

        {"role": "system", "content": system_prompt},

        {"role": "user", "content": f"Context:\n{context}\n\nQuestion:{user_input}"}

    ]


    try:
        response = generate_response(model, messages)
    except Exception as e:
        response = f"⚠️ Could not get a response right now. Please try again in a moment or switch to a different model.\n\n_Error: {e}_"


    st.session_state.messages.append(
        {"role": "assistant", "content": response}
    )

    st.chat_message("assistant").write(response)
    
    if used_sources:
        st.caption(f"📚 *Sources referenced:* {', '.join(used_sources)}")



    # SAVE TO SUPABASE ONLY IF USER LOGGED IN

    if st.session_state.user:

        saved, save_error = save_chat(
            st.session_state.user.id,
            st.session_state.current_session_id,
            user_input,
            response
        )
        if not saved:
            st.toast(f"⚠️ Chat could not be saved: {save_error}", icon="⚠️")
            
            if "relation \"chat_sessions\" does not exist" in str(save_error) or "column \"session_id\" of relation \"chats\" does not exist" in str(save_error):
                st.error("""
                **Database Setup Required!**
                To support chat sessions, please run this SQL query in your Supabase SQL Editor:
                
                ```sql
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now())
                );
                
                ALTER TABLE chats ADD COLUMN IF NOT EXISTS session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE;
                ```
                """)