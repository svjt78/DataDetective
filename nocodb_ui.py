import os
import re
import ast
import requests
import pandas as pd
import streamlit as st
import openai  # OpenAI for LLM query conversion
from rapidfuzz import fuzz  # For fuzzy matching

# ---------------------------
# HELPER FUNCTION: Balance Parentheses
# ---------------------------
def balance_parentheses(s: str) -> str:
    """Adds missing closing parentheses if the number of '(' is greater than ')'. """
    open_parens = s.count('(')
    close_parens = s.count(')')
    if open_parens > close_parens:
        s += ')' * (open_parens - close_parens)
    return s

# ---------------------------
# HELPER FUNCTION: Heuristic Column Renaming
# ---------------------------
def heuristic_rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each column whose name matches the generic pattern (e.g. "Field 2"),
    use the first non-null, non-empty value in that column as the new header.
    """
    new_columns = {}
    for col in df.columns:
        if re.match(r"^Field\s*\d+$", col):
            candidate_series = df[col].dropna()
            if not candidate_series.empty:
                candidate = candidate_series.iloc[0]
                if isinstance(candidate, str) and candidate.strip():
                    new_columns[col] = candidate.strip()
    df.rename(columns=new_columns, inplace=True)
    return df

# ---------------------------
# SETUP: Load API Keys
# ---------------------------
API_TOKEN = os.getenv("NOCODB_API_TOKEN")
if not API_TOKEN:
    st.error("Error: NOCODB_API_TOKEN is not set. Please configure it in your environment.")
    st.stop()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.warning("⚠️ OpenAI API Key is missing. The natural language query feature will not work.")
    st.stop()
openai.api_key = OPENAI_API_KEY  # Set OpenAI key

# ---------------------------
# NocoDB Configuration
# ---------------------------
BASE_API_URL = "http://localhost:8080/api/v2/tables/mywi4xbh6va660a/records"

# ---------------------------
# Function to Fetch All Data from NocoDB (Handles Pagination)
# ---------------------------
@st.cache_data(ttl=300)
def fetch_nocodb_data():
    headers = {"xc-token": API_TOKEN}
    all_records = []
    limit = 100
    page = 1

    while True:
        api_url = f"{BASE_API_URL}?page={page}&limit={limit}"
        try:
            response = requests.get(api_url, headers=headers)
            response.raise_for_status()
            data = response.json().get("list", [])
            if not data:
                break
            all_records.extend(data)
            if len(data) < limit:
                break
            page += 1
        except requests.exceptions.HTTPError as e:
            st.error(f"Error fetching data: {e}")
            return pd.DataFrame()
    return pd.DataFrame(all_records) if all_records else pd.DataFrame()

# ---------------------------
# Function: Identify Relevant Columns and Generate Filter Query with Detailed Reasoning
# ---------------------------
def convert_nl_to_query(nl_text, df_columns):
    """
    Uses OpenAI's GPT to convert a natural language query into a JSON object with two keys:
      "filter_code": a structured pandas filter code that applies fuzzy matching on selected columns.
                     In the generated code, use the placeholder {{THRESHOLD}} for the fuzzy threshold.
      "reasoning": a detailed explanation of the constructed query.
    """
    if not nl_text.strip():
        return None

    prompt = f"""
    You are a data filtering assistant. Given the natural language query below and the list of DataFrame columns,
    determine which columns should be filtered and what values to search for in each. Then produce a JSON object with two keys:
    
    "filter_code": A pandas expression that filters the DataFrame using fuzzy matching. For each relevant column,
      apply a lambda function that checks if the cell (if it is a string) has a fuzzy similarity score (using rapidfuzz.fuzz.partial_ratio)
      of at least {{THRESHOLD}} with the specified value (in a case-insensitive manner). Combine the conditions using an AND operator.
    
    "reasoning": Provide a detailed explanation including:
      - Which columns were selected and what values were extracted for each,
      - How fuzzy matching is applied (with a threshold placeholder {{THRESHOLD}} and case-insensitive),
      - And why an AND condition is used (i.e. all conditions must be met).
    
    Natural language query: "{nl_text}"
    DataFrame Columns: {list(df_columns)}
    
    For example, if the query is "find record types for start position of 24", a correct output might be:
    {{
      "filter_code": "df[(df['record type'].apply(lambda x: isinstance(x, str) and fuzz.partial_ratio('record type', x.lower()) >= {{THRESHOLD}})) & (df['Position Start'].apply(lambda x: isinstance(x, str) and fuzz.partial_ratio('24', x.lower()) >= {{THRESHOLD}}))]",
      "reasoning": "The query indicates that both the 'record type' and 'Position Start' columns are important. It searches for a fuzzy match to 'record type' in the 'record type' column and for '24' in the 'Position Start' column. Both conditions must be met, so they are combined with an AND operator."
    }}
    
    Return only the JSON object.
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        structured_response = response["choices"][0]["message"]["content"].strip()
        result = ast.literal_eval(structured_response)
        if "filter_code" in result and "reasoning" in result:
            return result
        else:
            return None
    except Exception as e:
        st.error(f"Error processing query: {e}")
        return None

# ---------------------------
# Function: Apply Fuzzy Filtering Based on Generated Filter Code
# ---------------------------
def apply_filter_code(df, filter_code):
    """
    Evaluates the filter code in a safe namespace.
    The filter_code should be an expression that uses the DataFrame 'df' and the function 'fuzz.partial_ratio'.
    """
    try:
        safe_globals = {
            "__builtins__": {
                "isinstance": isinstance,
                "str": str,
                "int": int,
                "float": float,
            },
            "fuzz": fuzz
        }
        local_vars = {"df": df}
        filtered_df = eval(filter_code, safe_globals, local_vars)
        return filtered_df
    except Exception as e:
        # Try to balance parentheses and re-evaluate
        balanced_code = balance_parentheses(filter_code)
        try:
            filtered_df = eval(balanced_code, safe_globals, local_vars)
            return filtered_df
        except Exception as e2:
            st.error(f"Error applying filter code after balancing: {e2}")
            return df

# ---------------------------
# Load Data and Apply Heuristic Renaming
# ---------------------------
df = fetch_nocodb_data()
if df.empty:
    st.warning("No data available from NocoDB.")
    st.stop()
df = heuristic_rename_columns(df)

# Allow local column renaming (display only)
if "column_renames" not in st.session_state:
    st.session_state["column_renames"] = {}
if st.session_state["column_renames"]:
    df.rename(columns=st.session_state["column_renames"], inplace=True)

# ---------------------------
# UI Title
# ---------------------------
st.title("📊 NocoDB Data Viewer with Natural Language Fuzzy Search")

# ---------------------------
# Sidebar: Fuzzy Matching Threshold Slider
# ---------------------------
st.sidebar.header("🔍 Filters")
threshold = st.sidebar.slider("Fuzzy Matching Threshold", min_value=0, max_value=100, value=70, step=1, key="threshold")

# ---------------------------
# Sidebar: Natural Language Query Input
# ---------------------------
st.sidebar.subheader("🗣️ Natural Language Query")
if "nl_query" not in st.session_state:
    st.session_state["nl_query"] = ""
nl_query = st.sidebar.text_area(
    "Enter your search in plain English",
    placeholder="Example: find record types for start position of 24"
)

# "Search" Button to Trigger Query
if st.sidebar.button("🔎 Search"):
    st.session_state["nl_query"] = nl_query
    st.rerun()

# Sidebar: Reset Filters Button
if st.sidebar.button("🔄 Reset Filters"):
    st.session_state["nl_query"] = ""
    st.rerun()

# ---------------------------
# Sidebar: Column Renaming Section
# ---------------------------
st.sidebar.markdown("### Rename Columns")
selected_column = st.sidebar.selectbox("Select column to rename", df.columns, key="rename_column")
new_name = st.sidebar.text_input("Enter new name for the selected column", key="new_column_name")
if st.sidebar.button("Apply Rename"):
    if new_name.strip():
        st.session_state["column_renames"][selected_column] = new_name.strip()
        st.success(f"Renamed '{selected_column}' to '{new_name.strip()}'")
        st.rerun()

# ---------------------------
# Apply LLM to Generate Filter Code and Detailed Reasoning
# ---------------------------
filtered_df = df.copy()
filter_details = None
if st.session_state["nl_query"].strip():
    filter_details = convert_nl_to_query(st.session_state["nl_query"], list(df.columns))
    if filter_details and "filter_code" in filter_details:
        # Substitute the placeholder {{THRESHOLD}} with the user-specified threshold.
        modified_filter_code = filter_details["filter_code"].format(THRESHOLD=threshold)
        filtered_df = apply_filter_code(df, modified_filter_code)
    else:
        st.info("No filter code was generated. Displaying full dataset.")

# ---------------------------
# Display Generated Filter Code and Detailed Reasoning in Sidebar (Below Column Renaming)
# ---------------------------
if filter_details:
    st.sidebar.subheader("Generated Filter Query")
    st.sidebar.code(filter_details.get("filter_code", "No filter code generated"), language="python")
    st.sidebar.subheader("Detailed Explanation")
    st.sidebar.text_area("Reasoning", value=filter_details.get("reasoning", "No reasoning provided"), height=250)

# ---------------------------
# Main Panel: Show Count of Filtered Records and Display Data
# ---------------------------
st.markdown(f"### Showing {filtered_df.shape[0]} of {df.shape[0]} records")
st.dataframe(filtered_df, use_container_width=True)
