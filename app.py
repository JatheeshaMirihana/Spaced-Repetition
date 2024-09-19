from __future__ import print_function
import datetime
import os.path
import pytz
import streamlit as st
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import googleapiclient.errors
import json
import os

# Google Calendar API scopes
SCOPES = ['https://www.googleapis.com/auth/calendar.events.readonly', 'https://www.googleapis.com/auth/calendar.events']

# Google Calendar API credentials from Streamlit secrets
CLIENT_ID = st.secrets["CLIENT_ID"]
CLIENT_SECRET = st.secrets["CLIENT_SECRET"]
REDIRECT_URI = st.secrets["REDIRECT_URI"]

@st.cache_data
def get_color_id(subject: str) -> str:
    subject = subject.lower()
    if subject in ['physics', 'p6']:
        return '7'  # Peacock
    elif subject in ['chemistry', 'chem']:
        return '6'  # Tangerine
    elif subject in ['combined maths', 'c.m.']:
        return '10'  # Basil
    else:
        return '1'  # Default (Lavender)

@st.cache_data
def convert_to_sri_lanka_time(dt: datetime.datetime) -> datetime.datetime:
    sri_lanka_tz = pytz.timezone('Asia/Colombo')
    return dt.astimezone(sri_lanka_tz)

def get_credentials():
    creds = None
    if 'token' not in st.session_state:
        st.session_state['token'] = None
    try:
        if st.session_state['token']:
            creds = Credentials.from_authorized_user_info(st.session_state['token'], SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = Flow.from_client_secrets_file('credentials.json', SCOPES)
                flow.redirect_uri = REDIRECT_URI
                auth_url, _ = flow.authorization_url(prompt='consent')
                st.markdown(f"[Click here to authorize]({auth_url})")
                
                # After user authorizes, get the code
                if 'code' in st.experimental_get_query_params():
                    flow.fetch_token(code=st.experimental_get_query_params()['code'][0])
                    creds = flow.credentials
                    st.session_state['token'] = creds.to_json()
                
                return creds
        return creds
    except Exception as e:
        st.error(f"An error occurred during authentication: {e}")
    return creds

# Function to retrieve event history
def get_event_history():
    if os.path.exists('event_history.json'):
        with open('event_history.json', 'r') as file:
            return json.load(file)
    else:
        return {'created_events': [], 'completed_events': [], 'missed_events': []}

# Function to save event history
def save_event_history(history):
    with open('event_history.json', 'w') as file:
        json.dump(history, file)

# Function to verify existing events
def verify_events(service, history):
    updated_history = {'created_events': [], 'completed_events': [], 'missed_events': []}
    for event in history['created_events']:
        if event_exists(service, event['id']):
            updated_history['created_events'].append(event)
        else:
            st.session_state.event_checkboxes.pop(event['id'], None)
    for event in history['completed_events']:
        if event_exists(service, event['id']):
            updated_history['completed_events'].append(event)
    for event in history['missed_events']:
        if event_exists(service, event['id']):
            updated_history['missed_events'].append(event)
    return updated_history

# Function to check if an event exists on Google Calendar
def event_exists(service, event_id):
    try:
        service.events().get(calendarId='primary', eventId=event_id).execute()
        return True
    except googleapiclient.errors.HttpError:
        return False

# Function to reset progress of all events
def reset_progress():
    updated_history = get_event_history()
    for event in updated_history['created_events']:
        for sub_event in event['sub_events']:
            sub_event['completed'] = False
    save_event_history(updated_history)
    st.session_state['event_history'] = updated_history

# Function to toggle event completion status
def toggle_completion(service, event_id, sub_event_id):
    history = get_event_history()
    for event in history['created_events']:
        if event['id'] == event_id:
            for sub_event in event['sub_events']:
                if sub_event['id'] == sub_event_id:
                    sub_event['completed'] = not sub_event['completed']
                    try:
                        calendar_event = service.events().get(calendarId='primary', eventId=sub_event_id).execute()
                        if 'originalColorId' not in sub_event:
                            sub_event['originalColorId'] = calendar_event.get('colorId', '1')
                        if sub_event['completed']:
                            calendar_event['summary'] = f"Completed: {calendar_event['summary']}"
                            calendar_event['colorId'] = '8'
                        else:
                            calendar_event['summary'] = calendar_event['summary'].replace("Completed: ", "")
                            calendar_event['colorId'] = sub_event['originalColorId']
                        service.events().update(calendarId='primary', eventId=sub_event_id, body=calendar_event).execute()
                    except googleapiclient.errors.HttpError as error:
                        st.error(f"An error occurred while updating event {sub_event_id}: {error}")
                    save_event_history(history)
                    st.session_state['event_history'] = history
                    return

# Function to render progress circle based on completed events
def render_progress_circle(event):
    total_sub_events = len(event['sub_events'])
    completed_sub_events = sum(1 for sub_event in event['sub_events'] if sub_event['completed'])
    
    circle_parts = []
    for i in range(total_sub_events):
        if i < completed_sub_events:
            circle_parts.append('<span style="color:green;">&#9679;</span>')
        else:
            circle_parts.append('<span style="color:lightgrey;">&#9675;</span>')
    
    return ' '.join(circle_parts)

# Function to sort events
def sort_events(events, sort_option):
    if sort_option == "Title":
        return sorted(events, key=lambda x: x['title'])
    elif sort_option == "Date":
        return sorted(events, key=lambda x: x['date'])
    elif sort_option == "Completion":
        return sorted(events, key=lambda x: sum(1 for sub_event in x['sub_events'] if sub_event['completed']), reverse=True)
    else:
        return events

# Main function to drive the Streamlit app
def main():
    creds = get_credentials()

    if not creds:
        st.error("Unable to authenticate. Please check your credentials and try again.")
        return

    try:
        service = build('calendar', 'v3', credentials=creds)
    except googleapiclient.errors.HttpError as error:
        st.error(f"An error occurred: {error}")
        return

    st.title('Google Calendar Event Scheduler')

    if 'event_history' not in st.session_state:
        history = get_event_history()
        updated_history = verify_events(service, history)
        if history != updated_history:
            save_event_history(updated_history)
        st.session_state['event_history'] = updated_history
    else:
        updated_history = st.session_state['event_history']

    st.sidebar.title('Your Progress')

    sort_option = st.sidebar.selectbox("Sort by:", ["Title", "Date", "Completion"], index=0)

    if 'event_checkboxes' not in st.session_state:
        st.session_state.event_checkboxes = {}

    sorted_events = sort_events(updated_history['created_events'], sort_option)

    for event in sorted_events:
        event_id = event['id']
        event_title = event['title']
        if len(event_title) > 20:
            event_title = event_title[:17] + "..."
        with st.sidebar.expander(f"{event_title}"):
            col1, col2 = st.columns([8, 1])
            with col1:
                st.markdown(render_progress_circle(event), unsafe_allow_html=True)
                for sub_event in event['sub_events']:
                    sub_event_id = sub_event['id']
                    is_completed = sub_event['completed']
                    event_name = sub_event['name']
                    if is_completed:
                        event_name = f"~~{event_name}~~"
                    st.checkbox(event_name, value=is_completed, key=f"cb_{sub_event_id}", on_change=toggle_completion, args=(service, event_id, sub_event_id))
            with col2:
                if st.button("🗑️", key=f"delete_main_{event_id}"):
                    try:
                        for sub_event in event['sub_events']:
                            service.events().delete(calendarId='primary', eventId=sub_event['id']).execute()
                        updated_history['created_events'] = [e for e in updated_history['created_events'] if e['id'] != event_id]
                        save_event_history(updated_history)
                        st.session_state['event_history'] = updated_history
                        st.sidebar.success(f"Deleted {event['title']} successfully!")
                    except googleapiclient.errors.HttpError as error:
                        st.error(f"An error occurred while deleting event {event_id}: {error}")

    selected_date = st.sidebar.date_input("Select a date to view events:")
    selected_events = [event for event in updated_history['created_events'] if event['date'] == str(selected_date)]

    st.write(f"Events for {selected_date}:")
    for event in selected_events:
        st.write(event['title'])

if __name__ == "__main__":
    main()
