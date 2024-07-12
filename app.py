import os
import re
import json
import base64
import streamlit as st
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from langchain_core.messages import AIMessage, HumanMessage
from langchain_community.utilities import SQLDatabase
from streamlit_option_menu import option_menu
from openai import OpenAI
import logging
from urllib.parse import quote_plus
from PIL import Image
from typing import List, Tuple
from streamlit_oauth import OAuth2Component

load_dotenv()

logging.basicConfig(level=logging.INFO)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Google OAuth2 Configuration
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8502" 
flow = Flow.from_client_config(
    {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    },
    scopes=SCOPES,
    redirect_uri=REDIRECT_URI
)

# Initialize the OAuth2Component
oauth2 = OAuth2Component(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI)

def get_table_and_columns(db: SQLDatabase, user_query: str) -> Tuple[str, List[str]]:
    schema = db.get_table_info()

    # Extract table names from schema
    table_names = re.findall(r'CREATE TABLE (\w+)', schema)

    # Simple keyword matching to find the most relevant table
    relevant_table = max(table_names, key=lambda table: sum(word.lower() in user_query.lower() for word in table.split('_')), default=None)

    if not relevant_table:
        return None, []

    # Extract column names for the relevant table
    table_schema = re.search(f'CREATE TABLE {relevant_table} \((.*?)\);', schema, re.DOTALL)
    if table_schema:
        columns = re.findall(r'(\w+)\s+\w+', table_schema.group(1))
        return relevant_table, columns

    return relevant_table, []

def clean_sql_query(query):
    return re.sub(r'^(SQL:?\s*)?', '', query, flags=re.IGNORECASE).strip()

def init_database(user: str, password: str, host: str, port: str, database: str) -> SQLDatabase:
    try:
        db_uri = f"mysql+mysqlconnector://{quote_plus(user)}:{quote_plus(password)}@{quote_plus(host)}:{quote_plus(port)}/{quote_plus(database)}"
        logging.info(f"Connecting to database with URI: {db_uri}")
        return SQLDatabase.from_uri(db_uri)
    except Exception as e:
        logging.error(f"Error connecting to database: {e}")
        return None
    
def get_sql_query(db: SQLDatabase, user_query: str, chat_history: List[dict]) -> str:
    table, columns = get_table_and_columns(db, user_query)

    if not table:
        return None

    prompt = f"""
    Based on the table '{table}' with columns {', '.join(columns)},
    generate a SQL query to answer: "{user_query}"
    Recent chat history: {chat_history[-3:] if len(chat_history) > 3 else chat_history}
    If the question has the word "latest" in it, the column name is "transaction_date"
    and if asked about the word "order" then the table is "purchase_order".
    Respond with only the SQL query, nothing else.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a SQL query generator."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0
        )
        return clean_sql_query(response.choices[0].message.content)
    except Exception as e:
        logging.error(f"Error generating SQL query: {e}")
        return None

def get_response(user_query: str, db: SQLDatabase, chat_history: list):
    try:
        sql_query = get_sql_query(db, user_query, chat_history)
        if not sql_query:
            return "I'm sorry, I couldn't generate a SQL query for your question."

        result = db.run(sql_query)

        prompt = f"""
        For the question: "{user_query}"
        The SQL query: {sql_query}
        Returned this result: {result}

        Provide a clear and concise answer to the user's question.
        """

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful data analyst."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Error in get_response: {e}")
        return "I'm sorry, I encountered an error while processing your request."

def authenticate_gmail():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def fetch_emails(service, query):
    try:
        result = service.users().messages().list(userId='me', q=query).execute()
        messages = result.get('messages', [])
        emails = []
        for msg in messages:
            msg = service.users().messages().get(userId='me', id=msg['id']).execute()
            payload = msg.get('payload', {})
            parts = payload.get('parts', [])
            for part in parts:
                if part.get('mimeType') == 'text/plain':
                    data = part.get('body', {}).get('data')
                    if data:
                        text = base64.urlsafe_b64decode(data.encode('ASCII')).decode('utf-8')
                        emails.append(text)
        return emails
    except Exception as e:
        logging.error(f"Error fetching emails: {e}")
        return []

def get_gmail_service():
    creds = authenticate_gmail()
    return build('gmail', 'v1', credentials=creds)

def main():
    st.set_page_config(page_title="Data Insights Chat", page_icon="🔍", layout="wide")

    
    st.markdown("""
    <style>
        .main {background-color: #f0f2f6;}
        .stApp {max-width: 1200px; margin: 0 auto;}
        .stButton>button {background-color: #4CAF50; color: white; border-radius: 5px;}
        .stTextInput>div>div>input {background-color: #ffffff;}
        .stChatMessage {background-color: #ffffff; border-radius: 10px; padding: 10px; margin-bottom: 10px;}
    </style>
    """, unsafe_allow_html=True)

    if 'user' not in st.session_state:
        st.session_state.user = None

    if st.session_state.user is None:
        authorization_url, _ = flow.authorization_url(prompt="consent")
        if st.button("Login with Google"):
            st.markdown(f'<a href="{authorization_url}" target="_self">Click here to login</a>', unsafe_allow_html=True)

        # Check if the user has returned from the OAuth flow
        if 'code' in st.query_params():
            code = st.query_params()['code'][0]
            flow.fetch_token(code=code)
            credentials = flow.credentials
            user_info = build('oauth2', 'v2', credentials=credentials).userinfo().get().execute()
            st.session_state.user = user_info
            st.experimental_rerun()
    else:
        # User is logged in
        st.write(f"Welcome, {st.session_state.user['name']}!")
        
        st.title("How can I help you?")

        with st.sidebar:
            image = Image.open('f.png')
            st.image(image, width=200)
            st.title("Data Insights Chat")
            
            selected = option_menu(
                menu_title="Main Menu",
                options=["Chat", "Database Connection", "Gmail Connection", "About"],
                icons=["chat-dots", "database", "envelope", "info-circle"],
                menu_icon="cast",
                default_index=0,
            )

        if "chat_history" not in st.session_state:
            st.session_state.chat_history = [
                AIMessage(content="Hello! I'm your data assistant. Ask me anything about your database."),
            ]

        if selected == "Chat":
            st.header("Chat with Your Data 💬")
            
            for message in st.session_state.chat_history:
                with st.chat_message("assistant" if isinstance(message, AIMessage) else "user"):
                    st.markdown(message.content)
            
            user_query = st.chat_input("Ask me about your data...")
            if user_query:
                st.session_state.chat_history.append(HumanMessage(content=user_query))
                
                with st.chat_message("user"):
                    st.markdown(user_query)
                
                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        response = get_response(user_query, st.session_state.get('db'), st.session_state.chat_history)
                    st.markdown(response)
                
                st.session_state.chat_history.append(AIMessage(content=response))

        elif selected == "Database Connection":
            st.header("Connect to Your Database 🔌")
            
            with st.form("db_connection"):
                host = st.text_input("Host", value="localhost")
                port = st.text_input("Port", value="3306")
                user = st.text_input("User", value="dev")
                password = st.text_input("Password", type="password")
                database = st.text_input("Database", value="mydatabase")
                
                if st.form_submit_button("Connect"):
                    with st.spinner("Connecting to database..."):
                        db = init_database(user, password, host, port, database)
                        if db:
                            st.session_state.db = db
                            st.success("🎉 Connected to database successfully!")
                        else:
                            st.error("❌ Failed to connect to the database. Please check your credentials and try again.")

        elif selected == "Gmail Connection":
            st.header("Connect to Your Gmail 📧")
            
            if "gmail_service" not in st.session_state:
                st.session_state.gmail_service = get_gmail_service()
            
            st.success("🎉 Connected to Gmail successfully!")
            email_query = st.text_input("Search Emails", placeholder="e.g., orders, payments, meetings")
            
            if st.button("Fetch Emails"):
                with st.spinner("Fetching emails..."):
                    emails = fetch_emails(st.session_state.gmail_service, email_query)
                    if emails:
                        st.write("Fetched Emails:")
                        for email in emails:
                            st.markdown(email)
                    else:
                        st.write("No emails found for the given query.")

        elif selected == "About":
            st.header("About Data Insights Chat 📊")
            st.write("""
            Data Insights Chat is an innovative tool that allows you to interact with your database using natural language.
            Simply connect to your database and start asking questions about your data!
            
            Key Features:
            - Natural language queries
            - Real-time SQL execution
            - User-friendly interface
            - Gmail integration
            
            Made with ❤️ by Dev
            """)

        if st.button("Logout"):
            st.session_state.user = None
            st.experimental_rerun()

if __name__ == "__main__":
    main()