from flask import Flask, request, jsonify
from flask_cors import CORS
import pyodbc
from datetime import datetime
import os
import re
import openai

app = Flask(__name__)
CORS(app)

def get_db_connection():
# Azure SQL Database configuration
    server = 'your_server_name.database.windows.net'
    database = 'your_database_name'
    username = 'your_username'
    password = 'your_password'
    driver = '{ODBC Driver 17 for SQL Server}'

    connection_string = f'DRIVER={driver};SERVER={server};DATABASE={database};UID={username};PWD={password}'
    conn = pyodbc.connect(connection_string)
    return conn

# Azure OpenAI configuration
openai.api_key = os.getenv('AZURE_OPENAI_API_KEY')


# Helper functions
def property_search(criteria):
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = "SELECT id, location, price, bedrooms, description FROM property WHERE true"

    if 'location' in criteria:
        query += "AND location ILIKE %s"
    if 'min_price' in criteria:
        query += "AND price >= %s"
    if 'max_price' in criteria:
        query += "AND price <= %s"
    if 'bedrooms' in criteria:
        query += "AND bedrooms = %s"

    cur.execute(query, [criteria.get('location', '%'), criteria.get('min_price', 0), criteria.get('max_price', 999999), criteria.get('bedrooms')])

    results = cur.fetchall()
    cur.close()
    conn.close()

    return results

def format_property(property):
    return f"ID: {property[0]}, Location: {property[1]}, Price: ${property[2]}, Bedrooms: {property[3]}"

def format_search_results(results):
    if not results:
        return "No properties found matching your criteria."
    return "\n".join(format_property(prop) for prop in results)

def get_property_details(property_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, location, price, bedrooms, description FROM property WHERE id = %s", (property_id,))
    property = cur.fetchone()
    cur.close()
    conn.close()
    if not property:
        return "Property not found."
    return f"Details for Property {property[0]}:\nLocation: {property[1]}\nPrice: ${property[2]}\nBedrooms: {property[3]}\nDescription: {property[4]}"

def schedule_viewing(property_id, date, time, user_email):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO viewing (property_id, date, time, user_email) VALUES (%s, %s, %s, %s)",
                (property_id, date, time, user_email))
    conn.commit()
    cur.close()
    conn.close()
    return f"Viewing scheduled for Property {property_id} on {date} at {time}. Confirmation sent to {user_email}."

def calculate_mortgage(principal, interest_rate, term_years):
    monthly_rate = interest_rate / 100 / 12
    num_payments = term_years * 12
    monthly_payment = principal * (monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)
    return round(monthly_payment, 2)

def get_faq_answer(question):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT answer FROM faq WHERE question ILIKE %s LIMIT 1", (f"%{question}%",))
    faq = cur.fetchone()
    cur.close()
    conn.close()
    if faq:
        return faq[0]
    return "I'm sorry, I don't have a specific answer for that question. Please contact our support team for more information."

# Main chat function
@app.route('/chat', methods=['GET'])
def chat():
    try:
        data = request.json
        user_message = data.get('message', '')
        chat_history = data.get('history', [])
        
        if 'search' in user_message.lower():
            criteria = extract_search_criteria(user_message)
            results = property_search(criteria)
            assistant_reply = format_search_results(results)
        elif 'details' in user_message.lower():
            property_id = extract_property_id(user_message)
            assistant_reply = get_property_details(property_id)
        elif 'schedule' in user_message.lower() or 'viewing' in user_message.lower():
            property_id, date, time, user_email = extract_viewing_info(user_message)
            assistant_reply = schedule_viewing(property_id, date, time, user_email)
        else:
            # Use OpenAI for general queries and FAQs
            messages = [{"role": "system", "content": "You are a helpful real estate assistant."}]
            messages.extend(chat_history)
            messages.append({"role": "user", "content": user_message})

            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.7,
                max_tokens=250
            )
            assistant_reply = response.choices[0].message.content

            # Check if it's a FAQ
            faq_answer = get_faq_answer(user_message)
            if faq_answer != "I'm sorry, I don't have a specific answer for that question.":
                assistant_reply = faq_answer

        return jsonify({
            "response": assistant_reply,
            "history": chat_history + [{"role": "user", "content": user_message},
                                       {"role": "assistant", "content": assistant_reply}]
        })

    except Exception as e:
        print(f"Error in chat route: {str(e)}")
        error_message = f"An error occurred: {str(e)}"
        if "quota" in str(e).lower():
            error_message = "We're experiencing high demand. Please try again later or contact our support team."
        return jsonify({"error": error_message}), 500

# Helper functions for extracting information from user messages
import openai

def extract_search_criteria(message):
    criteria = {}
    response = openai.Completion.create(
        model="text-davinci-003",
        prompt=f"Extract location, price range, and number of bedrooms from the following message: {message}",
        temperature=0.7,
        max_tokens=256
    )
    output = response.choices[0].text
    for line in output.splitlines():
        if "location" in line.lower():
            criteria["location"] = line.split(":")[1].strip()
        elif "price" in line.lower():
            prices = line.split(":")[1].strip().split(" to ")
            criteria["min_price"] = int(prices[0].replace("$", ""))
            criteria["max_price"] = int(prices[1].replace("$", ""))
        elif "bedrooms" in line.lower():
            criteria["bedrooms"] = int(line.split(":")[1].strip())
    return criteria

def extract_property_id(message):
    response = openai.Completion.create(
        model="text-davinci-003",
        prompt=f"Extract the property ID from the following message: {message}",
        temperature=0.7,
        max_tokens=256
    )
    output = response.choices[0].text
    match = re.search(r"ID: (\d+)", output)
    return int(match.group(1)) if match else None

def extract_viewing_info(message):
    response = openai.Completion.create(
        model="text-davinci-003",
        prompt=f"Extract the property ID, date, time, and user email from the following message: {message}",
        temperature=0.7,
        max_tokens=256
    )
    output = response.choices[0].text
    property_id = None
    date = None
    time = None
    user_email = None
    for line in output.splitlines():
        if "ID" in line:
            property_id = int(line.split(":")[1].strip())
        elif "date" in line.lower():
            date = line.split(":")[1].strip()
        elif "time" in line.lower():
            time = line.split(":")[1].strip()
        elif "email" in line.lower():
            user_email = line.split(":")[1].strip()
    return property_id, date, time, user_email


if __name__ == '__main__':
    app.run(debug=True)
