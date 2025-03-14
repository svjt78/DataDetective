import os
import requests
import pandas as pd
import streamlit as st

# Load API Token from Environment Variable
API_TOKEN = os.getenv("NOCODB_API_TOKEN")

if not API_TOKEN:
    st.error("Error: NOCODB_API_TOKEN is not set. Please configure it in your environment.")
    st.stop()

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
st.title("📊 NocoDB Data Viewer")

if df.empty:
    st.warning("No data available from NocoDB.")
    st.stop()

# Sidebar Filters
st.sidebar.header("🔍 Search & Filters")

# **1️⃣ Text Search Input**
search_text = st.sidebar.text_input("🔎 Search all columns", placeholder="Type to filter...")

# **2️⃣ Column-Specific Filters**
st.sidebar.subheader("📌 Column Filters")

column_filters = {}
for column in df.columns:
    unique_values = df[column].dropna().unique()
    if len(unique_values) > 1 and len(unique_values) < 50:  # Avoid filters for large datasets
        selected_value = st.sidebar.selectbox(f"Filter {column}", ["All"] + sorted(map(str, unique_values)), key=f"filter_{column}")
        column_filters[column] = selected_value if selected_value != "All" else None

# **3️⃣ Apply Filters to Data**
filtered_df = df.copy()

# **Apply Text Search**
if search_text.strip():
    search_text = search_text.lower()
    filtered_df = filtered_df[
        filtered_df.apply(lambda row: row.astype(str).str.contains(search_text, case=False, na=False).any(), axis=1)
    ]

# **Apply Column Filters**
for column, value in column_filters.items():
    if value:
        filtered_df = filtered_df[filtered_df[column].astype(str) == value]

# **Show Count of Filtered Records**
st.markdown(f"### Showing {filtered_df.shape[0]} of {df.shape[0]} records")

# **4️⃣ Display Filtered Data**
st.dataframe(filtered_df, use_container_width=True)

# **5️⃣ Reset Button**
if st.sidebar.button("🔄 Reset Filters"):
    for column in column_filters:
        st.session_state[f"filter_{column}"] = "All"
    st.session_state["search_text"] = ""
    st.experimental_rerun()
