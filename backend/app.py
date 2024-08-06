from flask import Flask, request, jsonify
import os
from openai import AzureOpenAI
from dotenv import load_dotenv

app = Flask(__name__)

load_dotenv()

client = AzureOpenAI(
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT"), 
    api_key=os.getenv("AZURE_OPENAI_KEY"),  
    api_version="2023-05-15"
)

DEPLOYMENT_NAME = "gpt-4"  # Replace with your actual deployment name

SYSTEM_MESSAGE = """
You are a helpful assistant for a real estate website. You can assist with:
1. Property searches based on criteria like location, price, size, etc.
2. Explaining real estate terms and processes.
3. Providing general advice about buying, selling, or renting properties.
4. Answering questions about mortgages and financing.
5. Scheduling property viewings or connecting users with real estate agents.
Always be polite and professional. If you're unsure about specific property details, suggest the user check the website's listings or contact a real estate agent for the most up-to-date information.
"""

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message', '')
    chat_history = data.get('history', [])

    messages = [{"role": "system", "content": SYSTEM_MESSAGE}]
    messages.extend(chat_history)
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=messages,
            temperature=0.7,
            max_tokens=250  # Increased for potentially longer real estate responses
        )

        assistant_reply = response.choices[0].message.content

        # Check for specific real estate queries that might need additional handling
        if "schedule viewing" in user_message.lower():
            assistant_reply += "\n\nTo schedule a viewing, please use our online booking system or contact one of our agents directly."
        elif "current market trends" in user_message.lower():
            assistant_reply += "\n\nFor the most up-to-date market trends, I recommend checking our monthly market report or speaking with one of our experienced agents."

        return jsonify({
            "response": assistant_reply,
            "history": messages + [{"role": "assistant", "content": assistant_reply}]
        })

    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        if "quota" in str(e).lower():
            error_message = "We're experiencing high demand. Please try again later or contact our support team."
        return jsonify({"error": error_message}), 500

if __name__ == '__main__':
    app.run(debug=True)