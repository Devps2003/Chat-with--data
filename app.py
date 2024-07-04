import os
import re
import json
import base64
import streamlit as st
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
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
# Load environment variables
load_dotenv()

# Initialize logging
logging.basicConfig(level=logging.INFO)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

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

# Streamlit UI
st.set_page_config(page_title="Data Insights Chat", page_icon="🔍", layout="wide")

# Apply custom CSS
st.markdown("""
<style>
    .main {background-color: #f0f2f6;}
    .stApp {max-width: 1200px; margin: 0 auto;}
    .stButton>button {background-color: #4CAF50; color: white; border-radius: 5px;}
    .stTextInput>div>div>input {background-color: #ffffff;}
    .stChatMessage {background-color: #ffffff; border-radius: 10px; padding: 10px; margin-bottom: 10px;}
</style>
""", unsafe_allow_html=True)

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
                response = get_response(user_query, st.session_state.db, st.session_state.chat_history)
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


    
# import os
# import re
# import json
# import base64
# import streamlit as st
# from dotenv import load_dotenv
# from google.oauth2.credentials import Credentials
# from google_auth_oauthlib.flow import InstalledAppFlow
# from googleapiclient.discovery import build
# from langchain_core.messages import AIMessage, HumanMessage
# from langchain_core.prompts import ChatPromptTemplate
# from langchain_core.runnables import RunnablePassthrough
# from langchain_community.utilities import SQLDatabase
# from streamlit_option_menu import option_menu
# from langchain_core.output_parsers import StrOutputParser
# from openai import OpenAI

# client = OpenAI(api_key="sk-proj-1bqKEBIPHmxAU0GbLuy8T3BlbkFJrnkLxuJBdn4YUMzKiydU")



# import logging
# from urllib.parse import quote_plus
# from PIL import Image

# # Initialize logging

# logging.basicConfig(level=logging.INFO)

# SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# def clean_sql_query(query):
#     cleaned_query = re.sub(r'^(SQL:?\s*)?', '', query, flags=re.IGNORECASE).strip()
#     return cleaned_query

# def init_database(user: str, password: str, host: str, port: str, database: str) -> SQLDatabase:
#     try:
#         user_encoded = quote_plus(user)
#         password_encoded = quote_plus(password)
#         host_encoded = quote_plus(host)
#         port_encoded = quote_plus(port)
#         database_encoded = quote_plus(database)
        
#         db_uri = f"mysql+mysqlconnector://{user_encoded}:{password_encoded}@{host_encoded}:{port_encoded}/{database_encoded}"
#         logging.info(f"Connecting to database with URI: {db_uri}")
#         return SQLDatabase.from_uri(db_uri)
#     except Exception as e:
#         logging.error(f"Error connecting to database: {e}")
#         st.error(f"Error connecting to database: {e}")
#         return None

# def get_sql_chain(db):
#     template = """
#         You are a data analyst at a company. You are interacting with a user who is asking questions about the company's database.
#         Based on the table schema below, write a SQL query that would answer the user's question. Take the conversation history into account.
        
#         <SCHEMA>{schema}</SCHEMA>
        
#         Important information:
#         - In all tables, the first entry is the latest, and the last entry is the oldest.
#         - Entries are sorted by time in descending order.
#         - When asked for "latest" or "recent" data, always use ORDER BY and LIMIT to get the most recent entries.
        
#         Conversation History: {chat_history}
        
#         Write only the SQL query and nothing else. Do not wrap the SQL query in any other text, not even backticks.
#         If the question is out of context, write an answer according to your knowledge.
        
#         For example:
#         Question: What are the latest orders?
#         SQL Query: SELECT * FROM orders ORDER BY order_date DESC LIMIT 5;
        
#         Your turn:
        
#         Question: {question}
#         SQL Query:
#         """
    
#     def openai_completion(prompt):
#         response = client.chat.completions.create(
#             model="gpt-3.5-turbo",
#             messages=[
#                 {"role": "system", "content": "You are a helpful assistant."},
#                 {"role": "user", "content": prompt}
#             ],
#             max_tokens=150,
#             temperature=0.0
#         )
#         return response.choices[0].message.content.strip()
    
#     def get_schema(_):
#         return db.get_table_info()
    
#     def generate_sql(query, chat_history):
#         schema = get_schema(None)
#         prompt = template.format(schema=schema, chat_history=chat_history, question=query)
#         return clean_sql_query(openai_completion(prompt))
    
#     return generate_sql

# def fallback_response(question: str, chat_history: list):
#     template = """
#     You are a knowledgeable AI assistant. The user asked a question that couldn't be answered using the database. 
#     Please provide a general answer based on your knowledge.

#     Conversation History: {chat_history}
#     User question: {question}

#     Please provide a helpful response:
#     """
    
#     prompt = template.format(chat_history=chat_history, question=question)
#     response = client.chat.completions.create(
#         model="gpt-3.5-turbo",
#         messages=[
#             {"role": "system", "content": "You are a helpful assistant."},
#             {"role": "user", "content": prompt}
#         ],
#         max_tokens=150,
#         temperature=0.0
#     )
    
#     return response.choices[0].message.content.strip()

# def get_response(user_query: str, db: SQLDatabase, chat_history: list):
#     sql_chain = get_sql_chain(db)
    
#     template = """
#         You are a data analyst at a company. You are interacting with a user who is asking questions about the company's database.
#         Based on the table schema below, question, sql query, and sql response, write a natural language response.
#         <SCHEMA>{schema}</SCHEMA>
    
#         Important information:
#         - In all tables, the first entry is the latest, and the last entry is the oldest.
#         - Entries are sorted by time in descending order.
#         - When discussing "latest" or "recent" data, always mention that you're providing the most recent entries.
    
#         Conversation History: {chat_history}
#         SQL Query: <SQL>{query}</SQL>
#         User question: {question}
#         SQL Response: {response}
        
#         Provide a clear and concise answer to the user's question based on the SQL response.
#         If the query returns multiple rows, summarize the data instead of listing all entries.
#         """
    
#     def openai_completion(prompt):
#         response = client.chat.completions.create(
#             model="gpt-3.5-turbo",
#             messages=[
#                 {"role": "system", "content": "You are a helpful assistant."},
#                 {"role": "user", "content": prompt}
#             ],
#             max_tokens=150,
#             temperature=0.0
#         )
#         return response.choices[0].message.content.strip()
    
#     def safe_db_run(vars):
#         try:
#             query = vars["query"]
#             result = db.run(query)
#             return f"Query executed successfully. Result: {result}"
#         except Exception as e:
#             logging.error(f"Error executing SQL query: {e}")
#             return None

#     def generate_response(vars):
#         schema = db.get_table_info()
#         prompt = template.format(schema=schema, chat_history=chat_history, query=vars["query"], question=user_query, response=vars["response"])
#         return openai_completion(prompt)
    
#     try:
#         query = sql_chain(user_query, chat_history)
#         response = safe_db_run({"query": query})
#         if response is None:
#             raise Exception("SQL query execution failed")
#         return generate_response({"query": query, "response": response})
#     except Exception as e:
#         logging.error(f"Error in main chain: {e}")
#         return fallback_response(user_query, chat_history)


# def authenticate_gmail():
#     creds = None
#     if os.path.exists('token.json'):
#         creds = Credentials.from_authorized_user_file('token.json', SCOPES)
#         # Remove cached token to ensure fresh authentication
#         os.remove('token.json')
#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             creds.refresh(Request())
#         else:
#             flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
#             creds = flow.run_local_server(port=0)
#         with open('token.json', 'w') as token:
#             token.write(creds.to_json())
#     return creds

# def fetch_emails(service, query):
#     try:
#         result = service.users().messages().list(userId='me', q=query).execute()
#         messages = result.get('messages', [])
#         emails = []
#         for msg in messages:
#             msg = service.users().messages().get(userId='me', id=msg['id']).execute()
#             payload = msg.get('payload', {})
#             headers = payload.get('headers', [])
#             parts = payload.get('parts', [])
#             for part in parts:
#                 if part.get('mimeType') == 'text/plain':
#                     data = part.get('body', {}).get('data')
#                     if data:
#                         text = base64.urlsafe_b64decode(data.encode('ASCII')).decode('utf-8')
#                         emails.append(text)
#         return emails
#     except Exception as e:
#         logging.error(f"Error fetching emails: {e}")
#         return []

# def get_gmail_service():
#     creds = authenticate_gmail()
#     service = build('gmail', 'v1', credentials=creds)
#     return service

# if "chat_history" not in st.session_state:
#     st.session_state.chat_history = [
#         AIMessage(content="Hello! I'm your data assistant. Ask me anything about your database."),
#     ]

# load_dotenv()

# st.set_page_config(page_title="Data Insights Chat", page_icon="🔍", layout="wide")
# st.markdown("""
# <style>
#     .main {
#         background-color: #f0f2f6;
#     }
#     .stApp {
#         max-width: 1200px;
#         margin: 0 auto;
#     }
#     .stButton>button {
#         background-color: #4CAF50;
#         color: white;
#         border-radius: 5px;
#     }
#     .stTextInput>div>div>input {
#         background-color: #ffffff;
#     }
#     .stChatMessage {
#         background-color: #ffffff;
#         border-radius: 10px;
#         padding: 10px;
#         margin-bottom: 10px;
#     }
# </style>
# """, unsafe_allow_html=True)


# st.title("How can I help you?")
# with st.sidebar:
#     image = Image.open('f.png')
#     st.image(image, width=200)
#     st.title("Data Insights Chat")
    
#     selected = option_menu(
#         menu_title="Main Menu",
#         options=["Chat", "Database Connection", "Gmail Connection", "About"],
#         icons=["chat-dots", "database", "envelope", "info-circle"],
#         menu_icon="cast",
#         default_index=0,
#     )

# if selected == "Chat":
#     st.header("Chat with Your Data 💬")
    
#     if "chat_history" not in st.session_state:
#         st.session_state.chat_history = [
#             AIMessage(content="Hello! I'm your data assistant. How can I help you today?"),
#         ]
    
#     for message in st.session_state.chat_history:
#         if isinstance(message, AIMessage):
#             with st.chat_message("assistant", avatar="🤖"):
#                 st.markdown(message.content)
#         elif isinstance(message, HumanMessage):
#             with st.chat_message("user", avatar="👤"):
#                 st.markdown(message.content)
    
#     user_query = st.chat_input("Ask me about your data...")
#     if user_query:
#         st.session_state.chat_history.append(HumanMessage(content=user_query))
        
#         with st.chat_message("user", avatar="👤"):
#             st.markdown(user_query)
        
#         with st.chat_message("assistant", avatar="🤖"):
#             with st.spinner("Thinking..."):
#                 response = get_response(user_query, st.session_state.db, st.session_state.chat_history)
#             st.markdown(response)
        
#         st.session_state.chat_history.append(AIMessage(content=response))

# elif selected == "Database Connection":
#     st.header("Connect to Your Database 🔌")
    
#     with st.form("db_connection"):
#         host = st.text_input("Host", value="localhost")
#         port = st.text_input("Port", value="3306")
#         user = st.text_input("User", value="dev")
#         password = st.text_input("Password", type="password", value="mypassword")
#         database = st.text_input("Database", value="mydatabase")
        
#         submitted = st.form_submit_button("Connect")
#         if submitted:
#             with st.spinner("Connecting to database..."):
#                 db = init_database(user, password, host, port, database)
#                 if db:
#                     st.session_state.db = db
#                     st.success("🎉 Connected to database successfully!")
#                 else:
#                     st.error("❌ Failed to connect to the database. Please check your credentials and try again.")

# elif selected == "Gmail Connection":
#     st.header("Connect to You Gmail 📧")
    
#     if "gmail_service" not in st.session_state:
#         st.session_state.gmail_service = get_gmail_service()
    
#     st.success("🎉 Connected to Gmail successfully!")
#     email_query = st.text_input("Search Emails", placeholder="e.g., orders, payments, meetings")
    
#     if st.button("Fetch Emails"):
#         with st.spinner("Fetching emails..."):
#             emails = fetch_emails(st.session_state.gmail_service, email_query)
#             if emails:
#                 st.write("Fetched Emails:")
#                 for email in emails:
#                     st.markdown(email)
#             else:
#                 st.write("No emails found for the given query.")
    
# elif selected == "About":
#     st.header("About Data Insights Chat 📊")
#     st.write("""
#     Data Insights Chat is an innovative tool that allows you to interact with your database using natural language.
#     Simply connect to your database and start asking questions about your data!
    
#     Key Features:
#     - Natural language queries
#     - Real-time SQL execution
#     - Fallback to general knowledge when needed
#     - User-friendly interface
    
#     Now, you can also connect your Gmail and ask questions about your emails!
    
#     Made with ❤️ by Dev
#     """)



# import os
# import re
# import json
# import base64
# import streamlit as st
# from dotenv import load_dotenv
# from google.oauth2.credentials import Credentials
# from google_auth_oauthlib.flow import InstalledAppFlow
# from googleapiclient.discovery import build
# from langchain_core.messages import AIMessage, HumanMessage
# from langchain_core.prompts import ChatPromptTemplate
# from langchain_core.runnables import RunnablePassthrough
# from langchain_community.utilities import SQLDatabase
# from streamlit_option_menu import option_menu
# from langchain_core.output_parsers import StrOutputParser
# from langchain_google_genai import ChatGoogleGenerativeAI
# import logging
# from urllib.parse import quote_plus
# from PIL import Image

# # Initialize logging
# logging.basicConfig(level=logging.INFO)

# SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# def clean_sql_query(query):
#     cleaned_query = re.sub(r'^(SQL:?\s*)?', '', query, flags=re.IGNORECASE).strip()
#     return cleaned_query

# def init_database(user: str, password: str, host: str, port: str, database: str) -> SQLDatabase:
#     try:
#         user_encoded = quote_plus(user)
#         password_encoded = quote_plus(password)
#         host_encoded = quote_plus(host)
#         port_encoded = quote_plus(port)
#         database_encoded = quote_plus(database)
        
#         db_uri = f"mysql+mysqlconnector://{user_encoded}:{password_encoded}@{host_encoded}:{port_encoded}/{database_encoded}"
#         logging.info(f"Connecting to database with URI: {db_uri}")
#         return SQLDatabase.from_uri(db_uri)
#     except Exception as e:
#         logging.error(f"Error connecting to database: {e}")
#         st.error(f"Error connecting to database: {e}")
#         return None

# def get_sql_chain(db):
#     template = """
#         You are a data analyst at a company. You are interacting with a user who is asking questions about the company's database.
#         Based on the table schema below, write a SQL query that would answer the user's question. Take the conversation history into account.
        
#         <SCHEMA>{schema}</SCHEMA>
        
#         Important information:
#         - In all tables, the first entry is the latest, and the last entry is the oldest.
#         - Entries are sorted by time in descending order.
#         - When asked for "latest" or "recent" data, always use ORDER BY and LIMIT to get the most recent entries.
        
#         Conversation History: {chat_history}
        
#         Write only the SQL query and nothing else. Do not wrap the SQL query in any other text, not even backticks.
#         If the question is out of context, write an answer according to your knowledge.
        
#         For example:
#         Question: What are the latest orders?
#         SQL Query: SELECT * FROM orders ORDER BY order_date DESC LIMIT 5;
        
#         Your turn:
        
#         Question: {question}
#         SQL Query:
#         """
    
#     prompt = ChatPromptTemplate.from_template(template)
    
#     gemini_api_key = os.getenv("GEMINI_API_KEY")
#     llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=gemini_api_key, convert_system_message_to_human=True, temperature=0.0)
    
#     def get_schema(_):
#         return db.get_table_info()
    
#     return (
#         RunnablePassthrough.assign(schema=get_schema)
#         | prompt
#         | llm
#         | StrOutputParser()
#         | (lambda x: clean_sql_query(x))
#     )

# def fallback_response(question: str, chat_history: list):
#     template = """
#     You are a knowledgeable AI assistant. The user asked a question that couldn't be answered using the database. 
#     Please provide a general answer based on your knowledge.

#     Conversation History: {chat_history}
#     User question: {question}

#     Please provide a helpful response:
#     """
    
#     prompt = ChatPromptTemplate.from_template(template)
    
#     gemini_api_key = os.getenv("GEMINI_API_KEY")
#     llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=gemini_api_key, convert_system_message_to_human=True, temperature=0.0)
    
#     chain = prompt | llm | StrOutputParser()
    
#     return chain.invoke({
#         "question": question,
#         "chat_history": chat_history,
#     })
   
# def get_response(user_query: str, db: SQLDatabase, chat_history: list):
#     sql_chain = get_sql_chain(db)
    
#     template = """
#         You are a data analyst at a company. You are interacting with a user who is asking questions about the company's database.
#         Based on the table schema below, question, sql query, and sql response, write a natural language response.
#         <SCHEMA>{schema}</SCHEMA>
    
#         Important information:
#         - In all tables, the first entry is the latest, and the last entry is the oldest.
#         - Entries are sorted by time in descending order.
#         - When discussing "latest" or "recent" data, always mention that you're providing the most recent entries.
    
#         Conversation History: {chat_history}
#         SQL Query: <SQL>{query}</SQL>
#         User question: {question}
#         SQL Response: {response}
        
#         Provide a clear and concise answer to the user's question based on the SQL response.
#         If the query returns multiple rows, summarize the data instead of listing all entries.
#         """
    
#     prompt = ChatPromptTemplate.from_template(template)
    
#     gemini_api_key = os.getenv("GEMINI_API_KEY")
#     llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=gemini_api_key, convert_system_message_to_human=True, temperature=0.0)
    
#     def safe_db_run(vars):
#         try:
#             query = vars["query"]
#             result = db.run(query)
#             return f"Query executed successfully. Result: {result}"
#         except Exception as e:
#             logging.error(f"Error executing SQL query: {e}")
#             print("Fallback mechanism called due to SQL execution error")
#             return None

#     chain = (
#         RunnablePassthrough.assign(query=sql_chain).assign(
#             schema=lambda _: db.get_table_info(),
#             response=safe_db_run,
#         )
#         | prompt
#         | llm
#         | StrOutputParser()
#     )
    
#     try:
#         result = chain.invoke({
#             "question": user_query,
#             "chat_history": chat_history,
#         })
#         return result
#     except Exception as e:
#         logging.error(f"Error in main chain: {e}")
#         print("Fallback mechanism called due to main chain error")
#         return fallback_response(user_query, chat_history)

# def authenticate_gmail():
#     creds = None
#     if os.path.exists('token.json'):
#         creds = Credentials.from_authorized_user_file('token.json', SCOPES)
#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             creds.refresh(Request())
#         else:
#             flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
#             creds = flow.run_local_server(port=0)
#         with open('token.json', 'w') as token:
#             token.write(creds.to_json())
#     return creds

# def fetch_emails(service, query):
#     try:
#         result = service.users().messages().list(userId='me', q=query).execute()
#         messages = result.get('messages', [])
#         emails = []
#         for msg in messages:
#             msg = service.users().messages().get(userId='me', id=msg['id']).execute()
#             payload = msg.get('payload', {})
#             headers = payload.get('headers', [])
#             parts = payload.get('parts', [])
#             for part in parts:
#                 if part.get('mimeType') == 'text/plain':
#                     data = part.get('body', {}).get('data')
#                     if data:
#                         text = base64.urlsafe_b64decode(data.encode('ASCII')).decode('utf-8')
#                         emails.append(text)
#         return emails
#     except Exception as e:
#         logging.error(f"Error fetching emails: {e}")
#         return []

# def get_gmail_service():
#     creds = authenticate_gmail()
#     service = build('gmail', 'v1', credentials=creds)
#     return service

# if "chat_history" not in st.session_state:
#     st.session_state.chat_history = [
#         AIMessage(content="Hello! I'm your data assistant. Ask me anything about your database."),
#     ]

# load_dotenv()

# st.set_page_config(page_title="Data Insights Chat", page_icon="🔍", layout="wide")
# st.markdown("""
# <style>
#     .main {
#         background-color: #f0f2f6;
#     }
#     .stApp {
#         max-width: 1200px;
#         margin: 0 auto;
#     }
#     .stButton>button {
#         background-color: #4CAF50;
#         color: white;
#         border-radius: 5px;
#     }
#     .stTextInput>div>div>input {
#         background-color: #ffffff;
#     }
#     .stChatMessage {
#         background-color: #ffffff;
#         border-radius: 10px;
#         padding: 10px;
#         margin-bottom: 10px;
#     }
# </style>
# """, unsafe_allow_html=True)


# st.title("How can I help you?")
# with st.sidebar:
#     image = Image.open('f.png')
#     st.image(image, width=200)
#     st.title("Data Insights Chat")
    
#     selected = option_menu(
#         menu_title="Main Menu",
#         options=["Chat", "Database Connection", "Gmail Connection", "About"],
#         icons=["chat-dots", "database", "envelope", "info-circle"],
#         menu_icon="cast",
#         default_index=0,
#     )

# if selected == "Chat":
#     st.header("Chat with Your Data 💬")
    
#     if "chat_history" not in st.session_state:
#         st.session_state.chat_history = [
#             AIMessage(content="Hello! I'm your data assistant. How can I help you today?"),
#         ]
    
#     for message in st.session_state.chat_history:
#         if isinstance(message, AIMessage):
#             with st.chat_message("assistant", avatar="🤖"):
#                 st.markdown(message.content)
#         elif isinstance(message, HumanMessage):
#             with st.chat_message("user", avatar="👤"):
#                 st.markdown(message.content)
    
#     user_query = st.chat_input("Ask me about your data...")
#     if user_query:
#         st.session_state.chat_history.append(HumanMessage(content=user_query))
        
#         with st.chat_message("user", avatar="👤"):
#             st.markdown(user_query)
        
#         with st.chat_message("assistant", avatar="🤖"):
#             with st.spinner("Thinking..."):
#                 response = get_response(user_query, st.session_state.db, st.session_state.chat_history)
#             st.markdown(response)
        
#         st.session_state.chat_history.append(AIMessage(content=response))

# elif selected == "Database Connection":
#     st.header("Connect to Your Database 🔌")
    
#     with st.form("db_connection"):
#         host = st.text_input("Host", value="localhost")
#         port = st.text_input("Port", value="3306")
#         user = st.text_input("User", value="Dev")
#         password = st.text_input("Password", type="password", value="FOS@123")
#         database = st.text_input("Database", value="erp_data")
        
#         submitted = st.form_submit_button("Connect")
#         if submitted:
#             with st.spinner("Connecting to database..."):
#                 db = init_database(user, password, host, port, database)
#                 if db:
#                     st.session_state.db = db
#                     st.success("🎉 Connected to database successfully!")
#                 else:
#                     st.error("❌ Failed to connect to the database. Please check your credentials and try again.")

# elif selected == "Gmail Connection":
#     st.header("Connect to Your Gmail 📧")
    
#     if "gmail_service" not in st.session_state:
#         st.session_state.gmail_service = get_gmail_service()
    
#     st.success("🎉 Connected to Gmail successfully!")
#     email_query = st.text_input("Search Emails", placeholder="e.g., orders, payments, meetings")
    
#     if st.button("Fetch Emails"):
#         with st.spinner("Fetching emails..."):
#             emails = fetch_emails(st.session_state.gmail_service, email_query)
#             if emails:
#                 st.write("Fetched Emails:")
#                 for email in emails:
#                     st.markdown(email)
#             else:
#                 st.write("No emails found for the given query.")
    
# elif selected == "About":
#     st.header("About Data Insights Chat 📊")
#     st.write("""
#     Data Insights Chat is an innovative tool that allows you to interact with your database using natural language.
#     Simply connect to your database and start asking questions about your data!
    
#     Key Features:
#     - Natural language queries
#     - Real-time SQL execution
#     - Fallback to general knowledge when needed
#     - User-friendly interface
    
#     Now, you can also connect your Gmail and ask questions about your emails!
    
#     Made with ❤️ by Dev
#     """)

