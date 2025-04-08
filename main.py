from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import json
import mysql.connector
import uuid
import os
from dotenv import load_dotenv
import datetime

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Database configuration
db_config = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}

# Connect to the database
def get_db_connection():
    return mysql.connector.connect(**db_config)

# Route to get all flashcards
@app.route('/flashcards', methods=['GET'])
def get_flashcards():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM flashcards")
        flashcards = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(flashcards)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Route to get a single flashcard by ID
@app.route('/flashcards/{flashcard_id}', methods=['GET'])
def get_flashcard(flashcard_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM flashcards WHERE id = %s", (flashcard_id,))
        flashcard = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if flashcard:
            return jsonify(flashcard)
        return jsonify({"error": "Flashcard not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Route to create a new flashcard
@app.route('/flashcards', methods=['POST'])
def create_flashcard():
    try:
        data = request.get_json()
        
        # Generate a unique ID
        flashcard_id = str(uuid.uuid4())
        
        # Get the current timestamp
        created_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Insert the new flashcard
        cursor.execute(
            "INSERT INTO flashcards (id, question, answer, created_at) VALUES (%s, %s, %s, %s)",
            (flashcard_id, data.get('question'), data.get('answer'), created_at)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # Return the created flashcard
        return jsonify({
            "id": flashcard_id,
            "question": data.get('question'),
            "answer": data.get('answer'),
            "created_at": created_at
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Route to update a flashcard
@app.route('/flashcards/<flashcard_id>', methods=['PUT'])
def update_flashcard(flashcard_id):
    try:
        data = request.get_json()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if the flashcard exists
        cursor.execute("SELECT * FROM flashcards WHERE id = %s", (flashcard_id,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"error": "Flashcard not found"}), 404
        
        # Update the flashcard
        cursor.execute(
            "UPDATE flashcards SET question = %s, answer = %s WHERE id = %s",
            (data.get('question'), data.get('answer'), flashcard_id)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # Return the updated flashcard
        return jsonify({
            "id": flashcard_id,
            "question": data.get('question'),
            "answer": data.get('answer')
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Route to delete a flashcard
@app.route('/flashcards/<flashcard_id>', methods=['DELETE'])
def delete_flashcard(flashcard_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if the flashcard exists
        cursor.execute("SELECT * FROM flashcards WHERE id = %s", (flashcard_id,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"error": "Flashcard not found"}), 404
        
        # Delete the flashcard
        cursor.execute("DELETE FROM flashcards WHERE id = %s", (flashcard_id,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"message": "Flashcard deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)
