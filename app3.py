import os
from dotenv import load_dotenv
load_dotenv()
import snowflake.connector
import requests
import logging
from flask import Flask, request, jsonify, abort, send_file
import datetime
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return send_file('index.html')

# Function to fetch data from Google Books API
def fetch_books_data(query, max_results=20):
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {
        "q": query,
        "maxResults": max_results,
        "startIndex": 0  # Start with the first result
    }
    all_books = []
    while True:
        response = requests.get(url, params=params)
        data = response.json()
        items = data.get("items", [])
        if not items:   
            break
        all_books.extend(items)
        params["startIndex"] += len(items)
    return all_books

# Function to connect to Snowflake and load data
def load_data_into_snowflake(data):
    try:
        conn = snowflake.connector.connect(
            user=os.getenv('SNOWFLAKE_USER'),
            password=os.getenv('SNOWFLAKE_PASSWORD'),
            account=os.getenv('SNOWFLAKE_ACCOUNT'),
            warehouse=os.getenv('SNOWFLAKE_WAREHOUSE'),
            database=os.getenv('SNOWFLAKE_DATABASE'),
            schema=os.getenv('SNOWFLAKE_SCHEMA')
        )

        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS books2 (
            title VARCHAR,
            authors VARCHAR,
            published_date DATE,
            description VARCHAR,
            categories VARCHAR
        )
        """)

        # Insert data into the table
        for item in data:
            volume_info = item.get("volumeInfo", {}) or None
            title = volume_info.get("title", "") or None
            authors = volume_info.get("authors", [])
            if not isinstance(authors, list):
                authors = [authors] if authors else []
            authors_str = ','.join(authors)  # Convert authors list to string

            published_date = volume_info.get("publishedDate", "")
            try:
                # Attempt to parse date
                parsed_date = datetime.datetime.strptime(published_date, "%Y-%m-%d")
                published_date = parsed_date.date()  # Extract date component
            except ValueError:
                
                published_date = None
            
            description = volume_info.get("description", "") or None
            
            categories = volume_info.get("categories", [])
            if not isinstance(categories, list):
                categories = [categories] if categories else []
            categories_str = ','.join(categories)  # Convert categories list to string

            cursor.execute("""
            INSERT INTO books2 (title, authors, published_date, description, categories)
            VALUES (%s, %s, %s, %s, %s)
            """, (title, authors_str, published_date, description, categories_str))
        conn.commit()
        cursor.close()
        conn.close()
    except snowflake.connector.errors.DatabaseError as e:
        logging.error(f"Error while loading data into Snowflake: {e}")
        abort(500, "Internal server error")

# Endpoint to handle book search
@app.route('/search-books', methods=['GET'])
def search_books():
    query = request.args.get('query')

    if not query:
        abort(400, "Query parameter 'query' is required")

    
    books_data = fetch_books_data(query, max_results=20)  
    load_data_into_snowflake(books_data)  # Load data into Snowflake

   
    return jsonify(books_data)

if __name__ == '__main__':
    app.run(debug=True)
