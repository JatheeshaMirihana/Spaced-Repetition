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
from dateutil.parser import isoparse

SCOPES = ['https://www.googleapis.com/auth/calendar.events.readonly', 'https://www.googleapis.com/auth/calendar.events']

# Utility function to get colorId based on subject
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

# Convert time to Sri Lanka timezone
@st.cache_data
def convert_to_sri_lanka_time(dt: datetime.datetime) -> datetime.datetime:
    sri_lanka_tz = pytz.timezone('Asia/Colombo')
    return dt.astimezone(sri_lanka_tz)

# Authentication Function to avoid repeated sign-ins
def get_credentials():
    creds = None
    
    # Check if credentials are already stored in session state
    if 'token' in st.session_state:
        creds = Credentials.from_authorized_user_info(json.loads(st.session_state['token']), SCOPES)
    
    # Refresh the token if necessary
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            st.error(f"Error refreshing credentials: {e}")
            creds = None

    # If no valid credentials, prompt user to authenticate
    if not creds or not creds.valid:
        client_config = {
            "web": {
                "client_id": st.secrets["client_id"],
                "client_secret": st.secrets["client_secret"],
                "redirect_uris": [st.secrets["redirect_uri"]],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        }

        flow = Flow.from_client_config(client_config, SCOPES)
        flow.redirect_uri = st.secrets["redirect_uri"]

        auth_url, _ = flow.authorization_url(prompt='consent')
        st.markdown(f"[Click here to authorize]({auth_url})")

        # After user authorizes, get the code from the URL and fetch the token
        if 'code' in st.experimental_get_query_params():
            try:
                code = st.experimental_get_query_params()['code'][0]
                flow.fetch_token(code=code)
                creds = flow.credentials
                st.session_state['token'] = creds.to_json()  # Save the credentials as a JSON string
            except Exception as e:
                st.error(f"Error fetching token: {e}")

    return creds

# Retrieve existing events from the Google Calendar
def get_existing_events(service, calendar_id='primary', time_min=None, time_max=None):
    try:
        events_result = service.events().list(calendarId=calendar_id, timeMin=time_min, timeMax=time_max, singleEvents=True, orderBy='startTime').execute()
        return events_result.get('items', [])
    except googleapiclient.errors.HttpError as error:
        st.error(f"An error occurred while fetching events: {error}")
        return []

# Get event history from a JSON file
def get_event_history():
    if os.path.exists('event_history.json'):
        with open('event_history.json', 'r') as file:
            return json.load(file)
    else:
        return {'created_events': [], 'completed_events': [], 'missed_events': []}

# Save event history to a JSON file
def save_event_history(history):
    with open('event_history.json', 'w') as file:
        json.dump(history, file)

# Verify existing events in Google Calendar with the saved history
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

# Check if a specific event exists on Google Calendar
def event_exists(service, event_id):
    try:
        service.events().get(calendarId='primary', eventId=event_id).execute()
        return True
    except googleapiclient.errors.HttpError:
        return False

# Function to reset progress in event history
def reset_progress():
    updated_history = get_event_history()
    for event in updated_history['created_events']:
        for sub_event in event['sub_events']:
            sub_event['completed'] = False
    save_event_history(updated_history)
    st.session_state['event_history'] = updated_history

# Function to toggle the completion status of a study sub-event
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
                            calendar_event['colorId'] = '8'  # Graphite
                        else:
                            calendar_event['summary'] = calendar_event['summary'].replace("Completed: ", "")
                            calendar_event['colorId'] = sub_event['originalColorId']
                        service.events().update(calendarId='primary', eventId=sub_event_id, body=calendar_event).execute()
                    except googleapiclient.errors.HttpError as error:
                        st.error(f"An error occurred while updating event {sub_event_id}: {error}")
                    save_event_history(history)
                    st.session_state['event_history'] = history
                    return

# Render the progress of an event as filled/unfilled circles
def render_progress_circle(event):
    total_sub_events = len(event['sub_events'])
    completed_sub_events = sum(1 for sub_event in event['sub_events'] if sub_event['completed'])
    
    circle_parts = []
    for i in range(total_sub_events):
        if i < completed_sub_events:
            circle_parts.append('<span style="color:green;">&#9679;</span>')  # filled circle
        else:
            circle_parts.append('<span style="color:lightgrey;">&#9675;</span>')  # unfilled circle
    
    return ' '.join(circle_parts)

# Sorting function to sort events
def sort_events(events, sort_option):
    if sort_option == "Title":
        return sorted(events, key=lambda x: x['title'])
    elif sort_option == "Date":
        return sorted(events, key=lambda x: x['date'])
    elif sort_option == "Completion":
        return sorted(events, key=lambda x: sum(1 for sub_event in x['sub_events'] if sub_event['completed']), reverse=True)
    else:
        return events

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

    # Load or verify event history
    if 'event_history' not in st.session_state:
        history = get_event_history()
        updated_history = verify_events(service, history)
        if history != updated_history:
            save_event_history(updated_history)
        st.session_state['event_history'] = updated_history
    else:
        updated_history = st.session_state['event_history']

    # Right Sidebar for Progress Tracker
    st.sidebar.title('Your Progress')

    # Add sorting dropdown
    sort_option = st.sidebar.selectbox("Sort by:", ["Title", "Date", "Completion"], index=0)

    if 'event_checkboxes' not in st.session_state:
        st.session_state.event_checkboxes = {}

    # Sort events based on selected option
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
                    checkbox_key = f"{event_id}-{sub_event_id}"
                    is_checked = st.session_state.event_checkboxes.get(checkbox_key, sub_event['completed'])
                    st.session_state.event_checkboxes[checkbox_key] = st.checkbox(sub_event['title'], value=is_checked, key=checkbox_key)
                    if st.session_state.event_checkboxes[checkbox_key] != sub_event['completed']:
                        toggle_completion(service, event_id, sub_event_id)
            with col2:
                st.button('↻', on_click=reset_progress)

if __name__ == '__main__':
    main()
