import streamlit as st

from models.llm import generate_response
from utils.rag import VectorStore
from utils.web_search import search_web
from utils.document_processor import process_uploaded_file
from utils.supabase_db import (
    login_user, signup_user, get_chat_history,
    save_chat, restore_user_session, logout_user,
    get_chat_sessions, create_chat_session, update_session_metadata
)
from utils.cloudinary_storage import upload_document_to_cloudinary


st.set_page_config(
    page_title="NeoStats Data Analyst AI",
    page_icon="📊",
    layout="wide"
)

# Load custom CSS
def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

try:
    load_css("assets/style.css")
except:
    pass

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

if "file_urls" not in st.session_state:
    st.session_state.file_urls = {}

if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None

if "schema_context" not in st.session_state:
    st.session_state.schema_context = ""

# --- RESTORE SESSION ON RELOAD ---
# This checks if we have stored auth tokens and restores the user session
if not st.session_state.user:
    restored = restore_user_session()
    if restored and st.session_state.user:
        pass # Default to a new chat upon reload 

# --- MAIN INTERFACE ---

# --- SIDEBAR UI ---
with st.sidebar:
    if st.button("➕ New Chat", use_container_width=True):
        st.session_state.current_session_id = None
        st.session_state.messages = []
        st.session_state.vector_store = VectorStore()
        st.session_state.uploaded_files = set()
        st.session_state.schema_context = ""
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
                    st.session_state.schema_context = ""
                    for chat in history:
                        st.session_state.messages.append({"role": "user", "content": chat["user_message"]})
                        st.session_state.messages.append({
                            "role": "assistant", 
                            "content": chat["ai_message"],
                            "sources": chat.get("sources") if chat.get("sources") is not None else []
                        })
                    
                    # Restore Context from Session
                    st.session_state.uploaded_files = set(s.get("uploaded_files", []))
                    st.session_state.file_urls = s.get("file_urls", {})
                    st.session_state.schema_context = s.get("schema_context", "")
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

# --- HEADER SECTION ---
st.markdown('<div class="main-header">', unsafe_allow_html=True)
col_title, _ = st.columns([0.65, 0.35])
with col_title:
    st.markdown("### 📊 NeoStats Data Analyst AI")

# --- MAIN CHAT UI CONTROLS ---
col_model, col_mode = st.columns([3, 0.8], gap="small")
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

st.divider()
st.markdown('</div>', unsafe_allow_html=True)

# --- STATIC ATTACHMENT SECTION (Per Screenshot) ---
with st.popover("📎 Attach", help="Add documents or context"):
    st.markdown("##### 📎 NeoStats Data Context")
    uploaded_file = st.file_uploader(
        "Upload Data Source",
        type=["txt", "csv", "pdf"],
        key="doc_uploader_main",
        label_visibility="collapsed"
    )
    st.divider()
    st.caption("Available Analyzers:")
    st.button("📊 SQL Schema Analyst", disabled=True, use_container_width=True, key="sql_ana_main")
    st.button("📈 Trend Optimizer", disabled=True, use_container_width=True, key="trend_opt_main")
    st.button("🧠 Deep RAG Search", disabled=True, use_container_width=True, key="rag_search_main")
    
    if uploaded_file and uploaded_file.name not in st.session_state.uploaded_files:
        with st.spinner("Processing..."):
            try:
                c_url, _ = upload_document_to_cloudinary(uploaded_file.getvalue(), uploaded_file.name)
                uploaded_file.seek(0)
                chunks, schema_info, error = process_uploaded_file(uploaded_file)
                if not error:
                    for chunk in chunks:
                        st.session_state.vector_store.add_document(chunk, metadata={"source": uploaded_file.name})
                    if schema_info:
                        st.session_state.schema_context += f"\n\nSource: {uploaded_file.name}\nSchema: {schema_info}"
                    st.session_state.uploaded_files.add(uploaded_file.name)
                    st.session_state.file_urls[uploaded_file.name] = c_url
                    
                    # Persist metadata to DB if session exists
                    if st.session_state.current_session_id:
                        update_session_metadata(
                            st.session_state.current_session_id, 
                            st.session_state.schema_context, 
                            st.session_state.uploaded_files,
                            file_urls=st.session_state.file_urls
                        )
                    for chunk in chunks:
                        st.session_state.vector_store.add_document(
                            chunk, 
                            metadata={"source": uploaded_file.name, "url": c_url}
                        )
                    st.rerun()
                else:
                    st.error(error)
            except Exception as e:
                st.error(f"Upload error: {e}")

# --- DATA CONTEXT INDICATOR ---
if st.session_state.uploaded_files:
    file_list = ", ".join(list(st.session_state.uploaded_files))
    st.caption(f"📚 **Active Files:** {file_list}")

# --- CHAT HISTORY AREA ---
chat_history_container = st.container()

with chat_history_container:
    # Always show welcome message at the top
    with st.chat_message("assistant"):
        st.markdown("""
        ### 👋 Welcome to NeoStats Data Analyst AI
        I am your specialized assistant for **SQL, PostgreSQL, MongoDB, and NoSQL** analytics.
        
        **How to get started:**
        1.  📎 **Upload your Data**: Use the 'Attach' button below to upload a **CSV**, **Table Schema**, or **SQL Documentation**.
        2.  🔍 **Analyze**: Ask me to write queries, explain trends, or optimize logic based on your data.
        3.  ⚖️ **Mode**: Toggle between **Concise** (quick SQL) and **Detailed** (deep reasoning) in the top menu.
        
        *Note: I am strictly specialized for data analysis and will only respond to analytics-related inquiries.*
        """)

    # Show existing history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg["role"] == "assistant" and msg.get("sources"):
                links = []
                for s in msg["sources"]:
                    if isinstance(s, dict):
                        name = s.get("name", "Unknown")
                        url = s.get("url", "")
                        links.append(f"[{name}]({url})" if url else name)
                    else:
                        links.append(str(s))
                st.caption(f"📚 *Sources referenced:* {', '.join(links)}")

# --- CHAT INPUT & ATTACHMENT ROW ---
input_row = st.container()
with input_row:
    if not st.session_state.uploaded_files:
        st.markdown(
            '<div class="compact-tip">📊 <b>NeoStats Tip:</b> Upload a CSV, Schema, or PDF for better insights.</div>', 
            unsafe_allow_html=True
        )
    
    # Optimized columns for the ChatGPT dock
    col_at, col_in = st.columns([0.65, 9.35], gap="small")
    with col_at:
        with st.popover("➕", help="Add documents or context"):
            st.markdown("##### 📎 NeoStats Data Context")
            uploaded_file = st.file_uploader(
                "Upload Data Source",
                type=["txt", "csv", "pdf"],
                key="doc_uploader_dock",
                label_visibility="collapsed"
            )
            st.divider()
            st.caption("Available Analyzers:")
            st.button("📊 SQL Schema Analyst", disabled=True, use_container_width=True, key="sql_ana_dock")
            st.button("📈 Trend Optimizer", disabled=True, use_container_width=True, key="trend_opt_dock")
            st.button("🧠 Deep RAG Search", disabled=True, use_container_width=True, key="rag_search_dock")
            
            if uploaded_file and uploaded_file.name not in st.session_state.uploaded_files:
                with st.spinner("Processing..."):
                    try:
                        c_url, _ = upload_document_to_cloudinary(uploaded_file.getvalue(), uploaded_file.name)
                        uploaded_file.seek(0)
                        chunks, schema_info, error = process_uploaded_file(uploaded_file)
                        if not error:
                            for chunk in chunks:
                                st.session_state.vector_store.add_document(chunk, metadata={"source": uploaded_file.name})
                            if schema_info:
                                st.session_state.schema_context += f"\n\nSource: {uploaded_file.name}\nSchema: {schema_info}"
                            st.session_state.uploaded_files.add(uploaded_file.name)
                            st.session_state.file_urls[uploaded_file.name] = c_url
                            
                            # Persist metadata to DB if session exists
                            if st.session_state.current_session_id:
                                from utils.supabase_db import update_session_metadata
                                update_session_metadata(
                                    st.session_state.current_session_id, 
                                    st.session_state.schema_context, 
                                    st.session_state.uploaded_files,
                                    file_urls=st.session_state.file_urls
                                )
                            for chunk in chunks:
                                st.session_state.vector_store.add_document(
                                    chunk, 
                                    metadata={"source": uploaded_file.name, "url": c_url}
                                )
                            st.rerun()
                        else:
                            st.error(error)
                    except Exception as e:
                        st.error(f"Upload error: {e}")

    with col_in:
        user_input = st.chat_input("Ask your analytics question...")

# Process input if it exists
if user_input:
    with chat_history_container:
        # 1. User Message
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)

        # 2. Assistant Response
        with st.chat_message("assistant"):
            with st.spinner("🧠 NeoStats Data Analyst AI is thinking..."):
                # RAG & Context Prep
                rag_results = st.session_state.vector_store.search(user_input)
                used_sources = []
                seen_sources = set()
                rag_context_parts = []
                
                for res in rag_results:
                    source_name = res["metadata"].get("source", "Unknown Document")
                    source_url = res["metadata"].get("url", "")
                    if source_name not in seen_sources:
                        used_sources.append({"name": source_name, "url": source_url})
                        seen_sources.add(source_name)
                    rag_context_parts.append(f"[Source: {source_name}]\n{res['text']}")
                rag_context = "\n\n".join(rag_context_parts)
                
                web_results = search_web(user_input)
                web_context_parts = []
                for res in web_results:
                    if res["title"] not in seen_sources:
                        used_sources.append({"name": res["title"], "url": res["url"]})
                        seen_sources.add(res["title"])
                    web_context_parts.append(f"[Web Source: {res['title']}]\n{res['body']}")
                web_context = "\n".join(web_context_parts)
                context = f"{rag_context}\n\n{web_context}"

                # Persona
                base_system_prompt = (
                    "You are the NeoStats Data Analyst AI, an expert specialized EXCLUSIVELY in data analytics, SQL (PostgreSQL, MySQL, SQLite), NoSQL, MongoDB queries, and business intelligence. "
                    "Strict Policy: You MUST only answer questions related to data analysis, SQL/NoSQL queries, data trends, or analytics documentation. "
                    "You are proficient in generating complex queries for MongoDB (Aggregations), PostgreSQL (JSONB, Window Functions), and other modern database systems. "
                    "If the user asks about ANY other topic, remind them you are an analytics specialist."
                )
                
                if mode == "Concise":
                    system_prompt = f"{base_system_prompt}\nGive short, precise answers focused on SQL queries."
                else:
                    system_prompt = f"{base_system_prompt}\nProvide detailed explanations of query logic and analytical reasoning."

                if st.session_state.schema_context:
                    system_prompt += f"\n\nAnalyzable Data Schema Knowledge:\n{st.session_state.schema_context}"

                full_prompt = f"Context:\n{st.session_state.schema_context}\n{context}\n\nQuestion: {user_input}"
                
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Context:\n{context}\n\nQuestion:{user_input}"}
                ]

                try:
                    response = generate_response(model, messages)
                except Exception as e:
                    response = f"⚠️ Could not get a response. Error: {e}"

                st.markdown(response)
                
                if used_sources:
                    links = [f"[{s['name']}]({s['url']})" if s['url'] else s['name'] for s in used_sources]
                    st.caption(f"📚 *Sources referenced:* {', '.join(links)}")
                
                # Save to history
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": response,
                    "sources": list(used_sources)
                })

                if st.session_state.user:
                    if not st.session_state.current_session_id:
                        title = user_input[:30] + "..." if len(user_input) > 30 else user_input
                        st.session_state.current_session_id = create_chat_session(st.session_state.user.id, title=title)
                    
                    saved, save_error = save_chat(
                        st.session_state.user.id, 
                        st.session_state.current_session_id, 
                        user_input, 
                        response,
                        sources=list(used_sources)
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
                            
                            ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS schema_context TEXT;
                            ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS uploaded_files JSONB DEFAULT '[]'::jsonb;
                            ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS file_urls JSONB DEFAULT '{}'::jsonb;
                            
                            ALTER TABLE chats ADD COLUMN IF NOT EXISTS session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE;
                            ALTER TABLE chats ADD COLUMN IF NOT EXISTS sources JSONB DEFAULT '[]'::jsonb;
                            ```
                            """)

    # All processing done for this interaction