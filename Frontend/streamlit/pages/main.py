import streamlit as st
import requests
from requests.auth import HTTPBasicAuth
import os

# --- Configuration ---
BASE_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="RAG Chatbot Portal", layout="wide")

# --- Session State Initialization ---
def init_session_state():
    """Initializes all required session state variables."""
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
    if 'role' not in st.session_state:
        st.session_state['role'] = None
    if 'username' not in st.session_state:
        st.session_state['username'] = ''
    if 'auth' not in st.session_state:
        st.session_state['auth'] = None
    if 'chat_history' not in st.session_state:
        st.session_state['chat_history'] = []

init_session_state()

# --- Authentication Logic ---
def login(role, username, password):
    """Handles the login logic and updates session state."""
    if not username or not password:
        st.sidebar.warning("Username and password are required.")
        return

    try:
        auth = HTTPBasicAuth(username, password)
        endpoint = "admin" if role == "Admin" else "user"
        res = requests.get(f"{BASE_URL}/{endpoint}/auth/check", auth=auth)

        if res.status_code == 200:
            st.session_state['logged_in'] = True
            st.session_state['role'] = role.lower()
            st.session_state['username'] = username
            st.session_state['auth'] = auth
            st.sidebar.success(f"{role} login successful!")
            st.rerun()
        else:
            st.sidebar.error(f"{role} login failed: {res.text}")
    except requests.exceptions.ConnectionError:
        st.sidebar.error(f"Connection Error: Is the backend server running at {BASE_URL}?")
    except Exception as e:
        st.sidebar.error(f"An unexpected error occurred: {e}")

def logout():
    """Clears session state to log the user out."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_session_state()
    st.rerun()

# --- Main Page UI ---
st.title("RAG Chatbot Portal")

if not st.session_state['logged_in']:
    st.sidebar.header("Login")
    login_role = st.sidebar.radio("Select role", ["User", "Admin"], key="login_role")
    login_username = st.sidebar.text_input("Username", key="login_username")
    login_password = st.sidebar.text_input("Password", type="password", key="login_password")
    if st.sidebar.button("Login", key="login_button"):
        login(login_role, login_username, login_password)

    with st.expander("New user? Register with a shared code"):
        reg_username = st.text_input("New username", key="reg_username")
        reg_password = st.text_input("New password", type="password", key="reg_password")
        reg_code = st.text_input("Registration code (provided by admin)", type="password", key="reg_code")
        if st.button("Register", key="register_button"):
            if not reg_username or not reg_password or not reg_code:
                st.warning("Please fill in username, password, and registration code.")
            else:
                try:
                    res = requests.post(
                        f"{BASE_URL}/user/register",
                        json={
                            "username": reg_username,
                            "password": reg_password,
                            "registration_code": reg_code,
                        },
                    )
                    if res.status_code == 200:
                        st.success("Registration successful. You can now log in as a user.")
                    else:
                        st.error(f"Registration failed: {res.text}")
                except requests.exceptions.ConnectionError:
                    st.error(f"Connection Error: Is the backend server running at {BASE_URL}?")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")

    st.info("Please log in to access the dashboards.")
else:
    st.sidebar.header(f"Welcome, {st.session_state['username']}!")
    st.sidebar.write(f"Role: {st.session_state['role'].capitalize()}")
    if st.sidebar.button("Logout"):
        logout()

    st.header("Welcome to the Portal")
    st.write("Please select a dashboard from the navigation menu on the left to get started.")
    if st.session_state['role'] == 'admin':
        st.write("Go to the **Admin Dashboard** to manage users, data, and system settings.")
    else:
        st.write("Go to the **User Dashboard** to chat with the RAG model and manage your documents.")