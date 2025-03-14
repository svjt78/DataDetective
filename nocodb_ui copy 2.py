import os
import requests
import pandas as pd
import streamlit as st
import openai  # OpenAI for NLP query conversion

# Load API Token from Environment Variable
API_TOKEN = os.getenv("NOCODB_API_TOKEN")

if not API_TOKEN:
    st.error("Error: NOCODB_API_TOKEN is not set. Please configure it in your environment.")
    st.stop()

# OpenAI API Key (Set this in your environment)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    st.warning("⚠️ OpenAI API Key is missing. The natural language query feature will not work.")
    st.stop()

openai.api_key = OPENAI_API_KEY  # Set OpenAI key

# NocoDB Local API Configuration
BASE_API_URL = "http://localhost:8080/api/v2/tables/mg0z1gkc06eo09b/records"

# Function to Fetch All Data from NocoDB (Handles Pagination using page and limit)
@st.cache_data(ttl=300)  # Cache data for 5 minutes
def fetch_nocodb_data():
    headers = {"xc-token": API_TOKEN}
    all_records = []
    limit = 100  # Number of records per page
    page = 1     # Start with page 1

    while True:
        api_url = f"{BASE_API_URL}?page={page}&limit={limit}"
        try:
            response = requests.get(api_url, headers=headers)
            response.raise_for_status()
            data = response.json().get("list", [])
            
            if not data:
                break  # No more records available

            all_records.extend(data)
            
            # If the number of records fetched is less than the limit, we've reached the last page.
            if len(data) < limit:
                break
            
            page += 1  # Move to the next page

        except requests.exceptions.HTTPError as e:
            st.error(f"Error fetching data: {e}")
            return pd.DataFrame()  # Return an empty DataFrame on error

    return pd.DataFrame(all_records) if all_records else pd.DataFrame()

# Load Data
df = fetch_nocodb_data()

# UI Title
st.title("📊 NocoDB Data Viewer with Natural Language Search")

if df.empty:
    st.warning("No data available from NocoDB.")
    st.stop()

# Sidebar Filters
st.sidebar.header("🔍 Filters")

# **1️⃣ Natural Language Search Input**
st.sidebar.subheader("🗣️ Natural Language Query")
if "nl_query" not in st.session_state:
    st.session_state["nl_query"] = ""

nl_query = st.sidebar.text_area("Enter your search in plain English", 
                                placeholder="Example: Show all orders above $500 after Jan 2024")

# **2️⃣ "Search" Button to Trigger Query**
if st.sidebar.button("🔎 Search"):
    st.session_state["nl_query"] = nl_query  # Store query in session state
    st.rerun()  # Force UI refresh to apply query

# **3️⃣ Function to Convert Natural Language to Structured Query**
def convert_nl_to_query(nl_text, df_columns):
    """
    Uses OpenAI's GPT to convert natural language queries into structured filters.
    """
    if not nl_text.strip():
        return None  # No query entered

    prompt = f"""
    You are a data filtering assistant. Convert the following natural language query into a structured pandas DataFrame filter:
    
    Query: "{nl_text}"
    
    DataFrame Columns: {list(df_columns)}

    Example conversions:
    - "Show all orders above $500" → df[df['order_amount'] > 500]
    - "Find customers from California" → df[df['state'] == 'California']
    - "List employees who joined after 2022" → df[df['join_date'] > '2022-01-01']
    
    Return only the structured filter code.
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",  # Use GPT-4 or GPT-3.5
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2  # Low temperature for deterministic results
        )
        structured_filter = response["choices"][0]["message"]["content"].strip()

        # Ensure the response is a valid filter query
        if "df[" in structured_filter:
            return structured_filter
        else:
            return None
    except Exception as e:
        st.error(f"Error processing query: {e}")
        return None

# **4️⃣ Apply NLP Query to Filter Data**
filtered_df = df.copy()

if st.session_state["nl_query"]:
    structured_query = convert_nl_to_query(st.session_state["nl_query"], df.columns)

    if structured_query:
        try:
            filtered_df = eval(structured_query)  # Apply generated filter dynamically
        except Exception as e:
            st.warning(f"⚠️ Could not apply filter: {e}")
            structured_query = None

# **5️⃣ Show Count of Filtered Records**
st.markdown(f"### Showing {filtered_df.shape[0]} of {df.shape[0]} records")

# **6️⃣ Display Filtered Data**
st.dataframe(filtered_df, use_container_width=True)

# **7️⃣ Reset Button**
if st.sidebar.button("🔄 Reset Filters"):
    st.session_state["nl_query"] = ""  # Clear natural language query in session state
    st.rerun()  # Corrected function to restart the Streamlit app
