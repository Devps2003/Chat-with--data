from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_community.utilities import SQLDatabase
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
import streamlit as st
import logging
from urllib.parse import quote_plus
import re
# Initialize logging
logging.basicConfig(level=logging.INFO)
def clean_sql_query(query):
    # Remove "SQL" or "SQL Query:" from the beginning of the query
    cleaned_query = re.sub(r'^(SQL:?\s*)?', '', query, flags=re.IGNORECASE).strip()
    return cleaned_query

def init_database(user: str, password: str, host: str, port: str, database: str) -> SQLDatabase:
    try:
        # URL-encode the components
        user_encoded = quote_plus(user)
        password_encoded = quote_plus(password)
        host_encoded = quote_plus(host)
        port_encoded = quote_plus(port)
        database_encoded = quote_plus(database)
        
        db_uri = f"mysql+mysqlconnector://{user_encoded}:{password_encoded}@{host_encoded}:{port_encoded}/{database_encoded}"
        logging.info(f"Connecting to database with URI: {db_uri}")
        return SQLDatabase.from_uri(db_uri)
    except Exception as e:
        logging.error(f"Error connecting to database: {e}")
        st.error(f"Error connecting to database: {e}")
        return None

def get_sql_chain(db):
    template = """
        You are a data analyst at a company. You are interacting with a user who is asking you questions about the company's database.
        Based on the table schema below, write a SQL query that would answer the user's question. Take the conversation history into account.
        
        <SCHEMA>{schema}</SCHEMA>
        
        Conversation History: {chat_history}
        
        Write only the SQL query and nothing else. Do not wrap the SQL query in any other text, not even backticks.
        If the question is out of context, write answer according to your knowledge.
        
        For example:
        Question: which 3 artists have the most tracks?
        SQL Query: SELECT ArtistId, COUNT(*) as track_count FROM Track GROUP BY ArtistId ORDER BY track_count DESC LIMIT 3;
        Question: Name 10 artists
        SQL Query: SELECT Name FROM Artist LIMIT 10;
        
        Your turn:
        
        Question: {question}
        SQL Query:
        """
    
    prompt = ChatPromptTemplate.from_template(template)
    
    gemini_api_key = "AIzaSyD6E3GE3r1ksnmYOAeYQRnvDJZMrMBihak"
    llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=gemini_api_key, convert_system_message_to_human=True, temperature=0.0)
    
    def get_schema(_):
        return db.get_table_info()
    
    return (
        RunnablePassthrough.assign(schema=get_schema)
        | prompt
        | llm
        | StrOutputParser()
        | (lambda x: clean_sql_query(x))
    )


def fallback_response(question: str, chat_history: list):
    template = """
    You are a knowledgeable AI assistant. The user asked a question that couldn't be answered using the database. 
    Please provide a general answer based on your knowledge.

    Conversation History: {chat_history}
    User question: {question}

    Please provide a helpful response:
    """
    
    prompt = ChatPromptTemplate.from_template(template)
    
    gemini_api_key = "AIzaSyD6E3GE3r1ksnmYOAeYQRnvDJZMrMBihak"
    llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=gemini_api_key, convert_system_message_to_human=True, temperature=0.0)
    
    chain = prompt | llm | StrOutputParser()
    
    return chain.invoke({
        "question": question,
        "chat_history": chat_history,
    })
   
def get_response(user_query: str, db: SQLDatabase, chat_history: list):
    sql_chain = get_sql_chain(db)
    
    template = """
        You are a data analyst at a company. You are interacting with a user who is asking you questions about the company's database.
        Based on the table schema below, question, sql query, and sql response, write a natural language response.
        <SCHEMA>{schema}</SCHEMA>
    
        Conversation History: {chat_history}
        SQL Query: <SQL>{query}</SQL>
        User question: {question}
        SQL Response: {response}
        
        Provide a clear and concise answer to the user's question based on the SQL response.
        """
    
    prompt = ChatPromptTemplate.from_template(template)
    
    gemini_api_key = "AIzaSyD6E3GE3r1ksnmYOAeYQRnvDJZMrMBihak"
    llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=gemini_api_key, convert_system_message_to_human=True, temperature=0.0)
    
    def safe_db_run(vars):
        try:
            query = vars["query"]
            result = db.run(query)
            return f"Query executed successfully. Result: {result}"
        except Exception as e:
            logging.error(f"Error executing SQL query: {e}")
            print("Fallback mechanism called due to SQL execution error")
            return None

    chain = (
        RunnablePassthrough.assign(query=sql_chain).assign(
            schema=lambda _: db.get_table_info(),
            response=safe_db_run,
        )
        | prompt
        | llm
        | StrOutputParser()
    )
    
    try:
        result = chain.invoke({
            "question": user_query,
            "chat_history": chat_history,
        })
        return result
    except Exception as e:
        logging.error(f"Error in main chain: {e}")
        print("Fallback mechanism called due to main chain error")
        return fallback_response(user_query, chat_history)

if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        AIMessage(content="Hello! I'm your data  assistant. Ask me anything about your database."),
    ]

load_dotenv()

st.set_page_config(page_title="Chat with Your Data", page_icon=":speech_balloon:")

st.title("Chat with your Data")

with st.sidebar:
    st.subheader("Settings")
    st.write("This is a simple chat application using MySQL. Connect to the database and start chatting.")
    
    host = st.text_input("Host", value="localhost", key="Host")
    port = st.text_input("Port", value="3306", key="Port")
    user = st.text_input("User", value="Dev", key="User")
    password = st.text_input("Password", type="password", value="FOS@123", key="Password")
    database = st.text_input("Database", value="erp_data", key="Database")
    
    if st.button("Connect"):
        logging.info(f"User input - Host: {host}, Port: {port}, User: {user}, Database: {database}")
        with st.spinner("Connecting to database..."):
            db = init_database(user, password, host, port, database)
            if db:
                st.session_state.db = db
                st.success("Connected to database!")
            else:
                st.error("Failed to connect to the database. Please check your credentials and try again.")
    
for message in st.session_state.chat_history:
    if isinstance(message, AIMessage):
        with st.chat_message("AI"):
            st.markdown(message.content)
    elif isinstance(message, HumanMessage):
        with st.chat_message("Human"):
            st.markdown(message.content)

user_query = st.chat_input("Type a message...")
if user_query is not None and user_query.strip() != "":
    st.session_state.chat_history.append(HumanMessage(content=user_query))
    
    with st.chat_message("Human"):
        st.markdown(user_query)
        
    with st.chat_message("AI"):
        response = get_response(user_query, st.session_state.db, st.session_state.chat_history)
        st.markdown(response)
        
    st.session_state.chat_history.append(AIMessage(content=response))
