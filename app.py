import asyncio
from quart import Quart, render_template, request, redirect, url_for, session, jsonify
from quart_cors import cors
import motor.motor_asyncio as motor
import urllib.parse as parser
import bcrypt
import re
import os
import datetime

app = Quart(__name__)
app = cors(app)
app.secret_key = os.urandom(24)

uname = parser.quote_plus("Rajat")
passwd = parser.quote_plus("2844")
cluster = "cluster0.gpq2duh"
url = f"mongodb+srv://{uname}:{passwd}@{cluster}.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsAllowInvalidCertificates=true"
client = motor.AsyncIOMotorClient(url)
db = client["Contacts"]
helplines = db["Helplines"]
accounts = db["Accounts"]
user_contacts_collection = db["User_contacts"]
trash_collection = db["Trash"] # Collection for deleted contacts


async def check_user_async(username: str) -> bool:
    try:
        chk_user = await accounts.find_one({"Username": username})
        return chk_user is not None
    except Exception as e:
        print(f"Error while checking username: {e}")
        return False


async def create_user_async(name, username, password, mobile):
    """Creates a new user account."""
    try:
        hashed_password = bcrypt.hashpw(
            password.encode('utf-8'), bcrypt.gensalt())
        user = {
            "Name": name,
            "Username": username,
            "Password": hashed_password,
            "Contact": mobile
        }
        await accounts.insert_one(user)
        return True, "User created successfully."
    except Exception as e:
        print(f"Error while creating user: {e}")
        return False, "An error occurred while creating the user."


async def validate_user_async(username, password):
    """Validates user credentials."""
    try:
        user = await accounts.find_one({"Username": username})
        if user and bcrypt.checkpw(password.encode('utf-8'), user['Password']):
            return True
        return False
    except Exception as e:
        print(f"Error while validating user: {e}")
        return False


async def get_contacts_async(username: str):
    """Retrieves contacts for a given username."""
    try:
        user_contacts = await user_contacts_collection.find_one({"Username": username})
        if user_contacts:
            return user_contacts.get("Contacts", [])
        return []
    except Exception as e:
        print(f"Error getting contacts: {e}")
        return []


async def get_contact_by_name_async(username: str, contact_name: str):
    """Retrieves a specific contact by name."""
    try:
        user_contacts = await user_contacts_collection.find_one({"Username": username})
        if user_contacts:
            for contact in user_contacts.get("Contacts", []):
                if contact.get("Name") == contact_name:
                    return contact
        return None
    except Exception as e:
        print(f"Error getting contact: {e}")
        return None


async def add_contact_async(username, name, mobile, email, job_title, company):
    """Adds a new contact to the user's list."""
    try:
        new_contact = {
            "Name": name,
            "Contact": mobile,
            "Email": email,
            "Job": job_title,
            "Company": company
        }
        await user_contacts_collection.update_one(
            {"Username": username},
            {"$push": {"Contacts": new_contact}},
            upsert=True
        )
        return True, "Contact added successfully."
    except Exception as e:
        print(f"Error adding contact: {e}")
        return False, "An error occurred while adding the contact."


async def update_contact_async(username, old_name, new_name, mobile, email, job_title, company):
    """Updates an existing contact."""
    try:
        user_doc = await user_contacts_collection.find_one({"Username": username})
        if user_doc:
            contacts = user_doc.get("Contacts", [])
            for contact in contacts:
                if contact.get("Name") == old_name:
                    contact['Name'] = new_name
                    contact['Contact'] = mobile
                    contact['Email'] = email
                    contact['Job'] = job_title
                    contact['Company'] = company
                    break

            await user_contacts_collection.update_one(
                {"Username": username},
                {"$set": {"Contacts": contacts}}
            )
            return True, "Contact updated successfully."
        return False, "Contact not found."
    except Exception as e:
        print(f"Error updating contact: {e}")
        return False, "An error occurred while updating the contact."


async def move_to_trash_async(username: str, contact_name: str):
    """Moves a contact to the trash collection."""
    try:
        user_doc = await user_contacts_collection.find_one({"Username": username})
        if not user_doc:
            return False, "User not found."

        contact_to_move = None
        for contact in user_doc.get("Contacts", []):
            if contact.get("Name") == contact_name:
                contact_to_move = contact
                break
        
        if not contact_to_move:
            return False, "Contact not found."

        trash_item = {
            "Username": username,
            "Contact": contact_to_move,
            "deleted_at": datetime.datetime.utcnow()
        }
        await trash_collection.insert_one(trash_item)

        await user_contacts_collection.update_one(
            {"Username": username},
            {"$pull": {"Contacts": {"Name": contact_name}}}
        )
        return True, "Contact moved to trash successfully."
    except Exception as e:
        print(f"Error moving contact to trash: {e}")
        return False, "An error occurred while moving the contact to trash."


async def get_trashed_contacts_async(username: str):
    """Retrieves trashed contacts for a given username, sorted by deletion date."""
    try:
        cursor = trash_collection.find({"Username": username})
        return await cursor.sort("deleted_at", -1).to_list(length=None)
    except Exception as e:
        print(f"Error getting trashed contacts: {e}")
        return []


async def restore_contact_async(username: str, contact_name: str):
    """Restores a contact from trash back to the user's contact list."""
    try:
        trashed_item = await trash_collection.find_one({"Username": username, "Contact.Name": contact_name})
        if not trashed_item:
            return False, "Contact not found in trash."

        contact_to_restore = trashed_item['Contact']

        await user_contacts_collection.update_one(
            {"Username": username},
            {"$push": {"Contacts": contact_to_restore}},
            upsert=True
        )

        await trash_collection.delete_one({"_id": trashed_item["_id"]})
        return True, "Contact restored successfully."
    except Exception as e:
        print(f"Error restoring contact: {e}")
        return False, "An error occurred while restoring the contact."


async def delete_permanently_async(username: str, contact_name: str):
    """Permanently deletes a contact from the trash."""
    try:
        result = await trash_collection.delete_one({"Username": username, "Contact.Name": contact_name})
        if result.deleted_count == 0:
            return False, "Contact not found in trash."
        return True, "Contact permanently deleted."
    except Exception as e:
        print(f"Error deleting contact permanently: {e}")
        return False, "An error occurred while deleting the contact."


async def empty_trash_async(username: str):
    """Permanently deletes all contacts from the trash for a given user."""
    try:
        await trash_collection.delete_many({"Username": username})
        return True, "Trash emptied successfully."
    except Exception as e:
        print(f"Error emptying trash: {e}")
        return False, "An error occurred while emptying the trash."


@app.route('/')
async def index():
    return jsonify({"message": "Welcome to the Contacts API!"})

@app.route('/api/register', methods=['POST'])
async def api_register():
    try:
        data = await request.get_json()
        name = data.get('name')
        username = data.get('username')
        password = data.get('password')
        mobile = data.get('mobile')

        if not all([name, username, password, mobile]):
            return jsonify({"error": "Missing required fields"}), 400

        if await check_user_async(username):
            return jsonify({"error": "Username already exists. Please choose a different one."}), 409
        
        success, message = await create_user_async(name, username, password, mobile)

        if success:
            return jsonify({"success": True, "message": "User registered successfully."}), 201
        else:
            return jsonify({"success": False, "error": message}), 500

    except Exception as e:
        print(f"Error in registration API: {e}")
        return jsonify({"success": False, "error": "An internal server error occurred."}), 500

# Add this new route to your existing app.py file.
@app.route('/api/login', methods=['POST'])
async def api_login():
    """
    Handles user login via a JSON API call from the frontend.
    """
    try:
        data = await request.get_json()
        username = data.get('username')
        password = data.get('password')

        # Basic input validation
        if not all([username, password]):
            return jsonify({"error": "Missing required fields"}), 400

        if await validate_user_async(username, password):
            # In a real-world scenario, you would manage sessions securely.
            # Here, we'll just return a success message.
            # You might return a token for the frontend to store.
            return jsonify({"success": True, "message": "Login successful"}), 200
        else:
            return jsonify({"success": False, "error": "Invalid username or password"}), 401
    
    except Exception as e:
        print(f"Error in login API: {e}")
        return jsonify({"success": False, "error": "An internal server error occurred."}), 500



@app.route('/api/contacts', methods=['GET'])
async def api_contacts():
    """
    Handles fetching contacts via a JSON API call from the frontend.
    It returns a list of contacts for the logged-in user.
    """
    try:
        if 'username' not in session:
            # Return a JSON error message if the user is not logged in.
            return jsonify({"error": "User not logged in"}), 401
        
        # Use the existing function to get the contacts for the current user.
        contacts_list = await get_contacts_async(session['username'])
        
        # Return the list of contacts as a JSON response.
        return jsonify(contacts_list), 200

    except Exception as e:
        print(f"Error fetching contacts in API: {e}")
        return jsonify({"error": "An internal server error occurred."}), 500


@app.route('/api/create_contact', methods=['POST'])
async def api_create_contact():
    """
    Handles creating a new contact via a JSON API call from the frontend.
    """
    try:
        if 'username' not in session:
            return jsonify({"error": "User not logged in"}), 401
        
        data = await request.get_json()
        name = data.get('name')
        mobile = data.get('mobile')
        email = data.get('email')
        job_title = data.get('job_title')
        company = data.get('company')
        
        # Basic input validation
        if not all([name, mobile]):
            return jsonify({"error": "Name and Mobile are required fields"}), 400
        
        # Call the existing function to add the contact
        await add_contact_async(session['username'], name, mobile, email, job_title, company)
        
        return jsonify({"success": True, "message": "Contact created successfully"}), 201
    
    except Exception as e:
        print(f"Error creating contact in API: {e}")
        return jsonify({"error": "An internal server error occurred."}), 500


@app.route('/edit_contact/<contact_name>', methods=['GET', 'POST'])
async def edit_contact(contact_name):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    contact = await get_contact_by_name_async(session['username'], contact_name)

    if request.method == 'POST':
        form = await request.form
        old_contact_name = form.get('old_contact_name')
        fname = form.get('fname')
        lname = form.get('lname')
        new_name = f"{fname} {lname}" if lname else fname
        mobile = form.get('mobile')
        email = form.get('email')
        job_title = form.get('job_title')
        company = form.get('company')

        await update_contact_async(
            session['username'],
            old_contact_name,
            new_name,
            mobile,
            email,
            job_title,
            company
        )

        return redirect(url_for('contacts'))

    if contact:
        name_parts = contact['Name'].split(' ', 1)
        contact['fname'] = name_parts[0]
        contact['lname'] = name_parts[1] if len(name_parts) > 1 else ''
    else:
        contact = {'fname': '', 'lname': '', 'Contact': '', 'Email': '', 'Job': '', 'Company': ''}

    return await render_template('edit_contact.html', contact=contact)


@app.route('/remove_contact/<contact_name>')
async def remove_contact(contact_name):
    if 'username' not in session:
        return redirect(url_for('login'))

    await move_to_trash_async(session['username'], contact_name)

    return redirect(url_for('contacts'))


@app.route('/trash')
async def trash_page():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    trashed_docs = await get_trashed_contacts_async(session['username'])
    
    # Format the 'deleted_at' timestamp for display
    for doc in trashed_docs:
        deleted_time = doc['deleted_at']
        now = datetime.datetime.utcnow()
        # Check if the date is today
        if deleted_time.date() == now.date():
            # Format as "Today, HH:MM AM/PM"
            doc['deleted_at_formatted'] = f"Today, {deleted_time.strftime('%I:%M %p')}"
        else:
            # Format as "Mon Day, YYYY"
            doc['deleted_at_formatted'] = deleted_time.strftime('%b %d, %Y')

    return await render_template('trash.html', trashed_docs=trashed_docs)


@app.route('/restore_contact/<contact_name>')
async def restore_contact(contact_name):
    if 'username' not in session:
        return redirect(url_for('login'))

    await restore_contact_async(session['username'], contact_name)
    return redirect(url_for('trash_page'))


@app.route('/delete_permanently/<contact_name>')
async def delete_permanently(contact_name):
    if 'username' not in session:
        return redirect(url_for('login'))

    await delete_permanently_async(session['username'], contact_name)
    return redirect(url_for('trash_page'))


@app.route('/empty_trash')
async def empty_trash():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    await empty_trash_async(session['username'])
    return redirect(url_for('trash_page'))


@app.route('/logout')
async def logout():
    session.pop('username', None)
    return redirect(url_for('index'))


@app.before_serving
async def initialize_db():
    try:
        count = await helplines.count_documents({})
        if count == 0:
            print("Database is empty. Seeding with initial contacts...")
            await helplines.insert_many([
                {"_id": "0000100", "Name": "Police", "Contact": "100"},
                {"_id": "0000108", "Name": "Ambulance", "Contact": "108"},
                {"_id": "0000101", "Name": "Fire Department", "Contact": "101"},
                {"_id": "00001098", "Name": "Child Helpline", "Contact": "1098"},
                {"_id": "00001077", "Name": "Disaster Management", "Contact": "1077"}
            ])
            print("Seeding complete.")
        else:
            print("Database already contains helpline data.")

    except Exception as e:
        print(f"Error during database initialization: {e}")

if __name__ == '__main__':
    app.run()
