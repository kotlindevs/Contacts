import asyncio
from quart import Quart, render_template, request, redirect, url_for, session
import motor.motor_asyncio as motor
import urllib.parse as parser
import bcrypt
import re
import os


app = Quart(__name__)
app.secret_key = os.urandom(24)

# MongoDB connection details
uname = parser.quote_plus("Rajat")
passwd = parser.quote_plus("2844")
cluster = "cluster0.gpq2duh"
url = f"mongodb+srv://{uname}:{passwd}@{cluster}.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsAllowInvalidCertificates=true"
client = motor.AsyncIOMotorClient(url)
db = client["Contacts"]
helplines = db["Helplines"]
accounts = db["Accounts"]
user_contacts_collection = db["User_contacts"]


async def check_user_async(username: str) -> bool:
    """Checks if a username already exists in the database."""
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
        return True
    except Exception as e:
        print(f"Error while creating user: {e}")
        return False


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
        # Find the user's document
        user_doc = await user_contacts_collection.find_one({"Username": username})
        if user_doc:
            # Find the contact within the contacts array
            contacts = user_doc.get("Contacts", [])
            for contact in contacts:
                if contact.get("Name") == old_name:
                    # Update the contact details
                    contact['Name'] = new_name
                    contact['Contact'] = mobile
                    contact['Email'] = email
                    contact['Job'] = job_title  # Add new field
                    contact['Company'] = company # Add new field
                    break

            # Update the entire contacts array in the document
            await user_contacts_collection.update_one(
                {"Username": username},
                {"$set": {"Contacts": contacts}}
            )
            return True, "Contact updated successfully."
        return False, "Contact not found."
    except Exception as e:
        print(f"Error updating contact: {e}")
        return False, "An error occurred while updating the contact."


async def remove_contact_async(username: str, contact_name: str):
    """Removes a contact from the user's list."""
    try:
        await user_contacts_collection.update_one(
            {"Username": username},
            {"$pull": {"Contacts": {"Name": contact_name}}}
        )
        return True, "Contact removed successfully."
    except Exception as e:
        print(f"Error removing contact: {e}")
        return False, "An error occurred while removing the contact."


@app.route('/')
async def index():
    return await render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
async def register():
    if 'username' in session:
        return redirect(url_for('contacts'))

    error = None
    if request.method == 'POST':
        form = await request.form
        name = form.get('name')
        username = form.get('username')
        password = form.get('password')
        mobile = form.get('mobile')

        if await check_user_async(username):
            error = "Username already exists. Please choose a different one."
        else:
            await create_user_async(name, username, password, mobile)
            return redirect(url_for('login'))

    return await render_template('register.html', error=error)


@app.route('/login', methods=['GET', 'POST'])
async def login():
    if 'username' in session:
        return redirect(url_for('contacts'))

    error = None
    if request.method == 'POST':
        form = await request.form
        username = form.get('username')
        password = form.get('password')

        if await validate_user_async(username, password):
            session['username'] = username
            return redirect(url_for('contacts'))
        else:
            error = "Invalid username or password"

    return await render_template('index.html', error=error)


@app.route('/contacts')
async def contacts():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    contacts_list = await get_contacts_async(session['username'])
    return await render_template('contacts.html', contacts=contacts_list)


@app.route('/create_contact', methods=['GET', 'POST'])
async def create_contact():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        form = await request.form
        name = form.get('name')
        mobile = form.get('mobile')
        email = form.get('email')
        job_title = form.get('job_title')
        company = form.get('company')
        
        await add_contact_async(session['username'], name, mobile, email, job_title, company)

        return redirect(url_for('contacts'))

    # Render the new create_contact.html file
    return await render_template('create_contact.html')


@app.route('/edit_contact/<contact_name>', methods=['GET', 'POST'])
async def edit_contact(contact_name):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    contact = await get_contact_by_name_async(session['username'], contact_name)

    if request.method == 'POST':
        form = await request.form
        old_contact_name = form.get('old_contact_name')
        # Correctly reconstruct the full name from the form data
        fname = form.get('fname')
        lname = form.get('lname')
        new_name = f"{fname} {lname}" if lname else fname
        mobile = form.get('mobile')
        email = form.get('email')
        job_title = form.get('job_title') # Get the new field
        company = form.get('company')   # Get the new field

        await update_contact_async(
            session['username'],
            old_contact_name,
            new_name,
            mobile,
            email,
            job_title, # Pass the new field
            company    # Pass the new field
        )

        return redirect(url_for('contacts'))

    # Added logic to handle single-word names gracefully
    if contact:
        name_parts = contact['Name'].split(' ', 1)
        contact['fname'] = name_parts[0]
        contact['lname'] = name_parts[1] if len(name_parts) > 1 else ''
    else:
        # Handle the case where the contact is not found
        contact = {'fname': '', 'lname': '', 'Contact': '', 'Email': '', 'Job': '', 'Company': ''}

    return await render_template('edit_contact.html', contact=contact)


@app.route('/remove_contact/<contact_name>')
async def remove_contact(contact_name):
    if 'username' not in session:
        return redirect(url_for('login'))

    success, message = await remove_contact_async(session['username'], contact_name)

    return redirect(url_for('contacts'))


@app.route('/logout')
async def logout():
    session.pop('username', None)
    return redirect(url_for('index'))


@app.before_serving
async def initialize_db():
    try:
        # Check and seed helplines
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
