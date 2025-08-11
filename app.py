import asyncio
from quart import Quart, render_template, request, redirect, url_for, session
import motor.motor_asyncio as motor
import urllib.parse as parser
import bcrypt
import re
import os

app = Quart(__name__)
app.secret_key = os.urandom(24)

uname = parser.quote_plus("Rajat")
passwd = parser.quote_plus("2844")
cluster = "cluster0.gpq2duh"
url = f"mongodb+srv://{uname}:{passwd}@{cluster}.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsAllowInvalidCertificates=true"
client = motor.AsyncIOMotorClient(url)
db = client["Contacts"]
helplines = db["Helplines"]
accounts = db["Accounts"]


async def check_user_async(username: str) -> bool:
    try:
        chk_user = await accounts.find_one({"Username": username})
        return chk_user is not None
    except Exception as e:
        print(f"Error while checking username: {e}")
        return False


async def create_user_async(name, username, password, mobile):
    try:
        hashed_password = bcrypt.hashpw(
            password.encode('utf-8'), bcrypt.gensalt())
        user = {
            "Name": name,
            "Username": username,
            "Password": hashed_password,
            "Contact": int(mobile) if re.match(r'^\d{10}$', mobile) else None,
            "Data": []
        }
        await accounts.insert_one(user)
        return True
    except Exception as e:
        print(f"Error while creating account: {e}")
        return False


async def verify_password_async(username, password):
    try:
        userdata = await accounts.find_one({"Username": username})
        if userdata:
            return bcrypt.checkpw(password.encode('utf-8'), userdata["Password"])
        return False
    except Exception as e:
        print(f"Error while verifying password: {e}")
        return False


async def get_user_contacts_async(username):
    user_doc = await accounts.find_one({"Username": username})
    if user_doc and user_doc.get("Data"):
        return user_doc["Data"]
    return []


async def create_contact_async(username: str, fname, lname, mobile, email):
    try:
        contact_data = {
            "Name": f"{fname} {lname}".strip(),
            "Contact": mobile,
            "Email": email
        }
        await accounts.update_one(
            {"Username": username},
            {"$push": {"Data": contact_data}}
        )
        return True, "Contact created successfully."
    except Exception as e:
        return False, f"Error creating contact: {e}"


async def remove_contact_async(username: str, contact_name):
    try:
        await accounts.update_one(
            {"Username": username},
            {"$pull": {"Data": {"Name": contact_name}}}
        )
        return True, f"Contact '{contact_name}' removed successfully."
    except Exception as e:
        return False, f"Error removing contact: {e}"


async def get_contact_by_name_async(username: str, contact_name: str):
    user_doc = await accounts.find_one({"Username": username})
    if user_doc and user_doc.get("Data"):
        for contact in user_doc["Data"]:
            if contact["Name"] == contact_name:
                return contact
    return None


async def update_contact_async(username: str, old_contact_name: str, new_fname: str, new_lname: str, new_mobile: str, new_email: str):
    new_contact_name = f"{new_fname} {new_lname}".strip()
    try:
        await accounts.update_one(
            {"Username": username, "Data.Name": old_contact_name},
            {"$set": {
                "Data.$.Name": new_contact_name,
                "Data.$.Contact": new_mobile,
                "Data.$.Email": new_email
            }}
        )
        return True, "Contact updated successfully."
    except Exception as e:
        return False, f"Error updating contact: {e}"


@app.route('/')
async def index():
    if 'username' in session:
        return redirect(url_for('contacts'))
    return await render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
async def login():
    if 'username' in session:
        return redirect(url_for('contacts'))

    error = None
    success = request.args.get('success')

    if request.method == 'POST':
        form = await request.form
        username = form.get('username')
        password = form.get('password')

        if await verify_password_async(username, password):
            session['username'] = username
            return redirect(url_for('contacts'))

        error = 'Invalid username or password.'

    return await render_template('index.html', error=error, success=success)


@app.route('/register', methods=['GET', 'POST'])
async def register():
    error = None
    if request.method == 'POST':
        form = await request.form
        name = form.get('name')
        username = form.get('username')
        password = form.get('password')
        mobile = form.get('mobile')

        if await check_user_async(username):
            error = 'Username already exists.'
            return await render_template('register.html', error=error)

        if await create_user_async(name, username, password, mobile):
            return redirect(url_for('login', success='Account created successfully!'))
        else:
            error = 'An error occurred during registration.'
            return await render_template('register.html', error=error)

    return await render_template('register.html')


@app.route('/contacts')
async def contacts():
    if 'username' not in session:
        return redirect(url_for('login'))

    user_contacts = await get_user_contacts_async(session['username'])
    return await render_template('contacts.html', contacts=user_contacts)


@app.route('/create_contact', methods=['POST'])
async def create_contact():
    if 'username' not in session:
        return redirect(url_for('login'))

    form = await request.form
    fname = form.get('fname')
    lname = form.get('lname')
    mobile = form.get('mobile')
    email = form.get('email')

    if fname and mobile:
        success, message = await create_contact_async(session['username'], fname, lname, mobile, email)

    return redirect(url_for('contacts'))


@app.route('/edit_contact/<contact_name>', methods=['GET', 'POST'])
async def edit_contact(contact_name):
    if 'username' not in session:
        return redirect(url_for('login'))

    contact = await get_contact_by_name_async(session['username'], contact_name)
    if not contact:
        return redirect(url_for('contacts'))

    if request.method == 'POST':
        form = await request.form
        fname = form.get('fname')
        lname = form.get('lname')
        mobile = form.get('mobile')
        email = form.get('email')

        if fname and mobile:
            success, message = await update_contact_async(
                session['username'],
                contact_name,
                fname,
                lname,
                mobile,
                email
            )

        return redirect(url_for('contacts'))

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
        count = await helplines.count_documents({})
        if count == 0:
            print("Database is empty. Seeding with initial contacts...")
            await helplines.insert_many([
                {"_id": "0000100", "Name": "Police", "Contact": "100"},
                {"_id": "0000108", "Name": "Ambulance", "Contact": "108"},
                {"_id": "0000101", "Name": "Fire Department", "Contact": "101"},
                {"_id": "00001098", "Name": "Child Helpline", "Contact": "1098"},
                {"_id": "00001091", "Name": "Women's Helpline", "Contact": "1091"},
                {"_id": "0000112", "Name": "All-in-One Emergency", "Contact": "112"},
            ])
    except Exception as e:
        print(f"Error during database initialization: {e}")

if __name__ == '__main__':
    app.run()
