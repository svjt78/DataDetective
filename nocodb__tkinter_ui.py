import os
import requests
import tkinter as tk
from tkinter import ttk

# Load API Token from Environment Variable
API_TOKEN = os.getenv("NOCODB_API_TOKEN")

if not API_TOKEN:
    print("Error: NOCODB_API_TOKEN is not set. Please configure it in your environment.")
    exit(1)

# NocoDB Local API Configuration
API_URL = "http://localhost:8080/api/v2/tables/mi0a8csf619rns4/records"

# Function to Fetch Data from NocoDB
def fetch_nocodb_data():
    headers = {"xc-token": API_TOKEN}
    try:
        response = requests.get(API_URL, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data.get("list", [])  # Extracting records from response
    except requests.exceptions.RequestException as e:
        print("Error fetching data:", e)
        return []

# Function to Populate Table
def populate_table(data):
    """Populate the table with the given data."""
    table.delete(*table.get_children())  # Clear table before inserting new data
    for record in data:
        values = list(record.values())  # Convert dictionary values to list
        table.insert("", "end", values=values)

# Function to Handle Search
def search():
    query = search_entry.get().strip().lower()
    
    if query == "":
        # Reset table to original data if search box is empty
        populate_table(records)
    else:
        # Filter records based on search query
        filtered_records = [
            record for record in records 
            if query in " ".join(map(str, record.values())).lower()
        ]
        populate_table(filtered_records)

# GUI Initialization
root = tk.Tk()
root.title("NocoDB Data Viewer (Local Instance)")
root.geometry("800x500")

# Search Bar
search_frame = tk.Frame(root)
search_frame.pack(pady=10)

search_label = tk.Label(search_frame, text="Search:")
search_label.pack(side=tk.LEFT, padx=5)

search_entry = tk.Entry(search_frame, width=50)
search_entry.pack(side=tk.LEFT, padx=5)

search_button = tk.Button(search_frame, text="Search", command=search)
search_button.pack(side=tk.LEFT, padx=5)

# Table Frame
table_frame = tk.Frame(root)
table_frame.pack(fill=tk.BOTH, expand=True)

# Table View
table = ttk.Treeview(table_frame)
table.pack(fill=tk.BOTH, expand=True)

# Fetch Data & Initialize Table
records = fetch_nocodb_data()

if records:
    columns = list(records[0].keys())  # Extract column names
    table["columns"] = columns
    table["show"] = "headings"

    for col in columns:
        table.heading(col, text=col)
        table.column(col, anchor="center")

    populate_table(records)  # Display Data

root.mainloop()
