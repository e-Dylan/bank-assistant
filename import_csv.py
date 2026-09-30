import sqlite3
import pandas as pd

# Define your file paths
csv_file = "data/transactions.csv"  # Replace with your CSV file name
db_file = "db.db"  # Replace with your target SQLite database name
table_name = "transactions"  # The name of the table you want to create/fill

# Connect to SQLite (it will create the database file if it doesn't exist)
conn = sqlite3.connect(db_file)

# Read the CSV file into a pandas DataFrame
# Note: If pandas is not installed, run 'pip install pandas' in your VS Code terminal first
df = pd.read_csv(csv_file)

# Write the data to the SQLite table
# 'fail', 'replace', or 'append' based on your preference
df.to_sql(table_name, conn, if_exists="replace", index=False)

# Close the connection
conn.close()
print(f"Successfully imported {len(df)} rows into the '{table_name}' table!")
