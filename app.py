from __future__ import print_function
import datetime
import os.path
import pytz
import streamlit as st
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import googleapiclient.errors
import google.auth.exceptions
from dateutil.parser import isoparse
import json

SCOPES = ['https://www.googleapis.com/auth/calendar.events.readonly', 'https://www.googleapis.com/auth/calendar.events']

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
    try:
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
    except Exception as e:
        st.error(f"An error occurred during authentication: {e}")
    return creds

def get_existing_events(service, calendar_id='primary', time_min=None, time_max=None):
    try:
        events_result = service.events().list(calendarId=calendar_id, timeMin=time_min, timeMax=time_max, singleEvents=True, orderBy='startTime').execute()
        return events_result.get('items', [])
    except googleapiclient.errors.HttpError as error:
        st.error(f"An error occurred while fetching events: {error}")
        return []

def get_event_history():
    if os.path.exists('event_history.json'):
        with open('event_history.json', 'r') as file:
            return json.load(file)
    else:
        return {'created_events': [], 'completed_events': [], 'missed_events': []}

def save_event_history(history):
    with open('event_history.json', 'w') as file:
        json.dump(history, file)

def verify_events(service, history):
    updated_history = {'created_events': [], 'completed_events': [], 'missed_events': []}
    for event in history['created_events']:
        if event_exists(service, event['id']):
            updated_history['created_events'].append(event)
        else:
            # Event doesn't exist on calendar, remove from progress bar
            st.session_state.event_checkboxes.pop(event['id'], None)
    for event in history['completed_events']:
        if event_exists(service, event['id']):
            updated_history['completed_events'].append(event)
    for event in history['missed_events']:
        if event_exists(service, event['id']):
            updated_history['missed_events'].append(event)
    return updated_history

# Function to check if event exists on Google Calendar
def event_exists(service, event_id):
    try:
        service.events().get(calendarId='primary', eventId=event_id).execute()
        return True
    except googleapiclient.errors.HttpError:
        return False

def reset_progress():
    updated_history = get_event_history()
    for event in updated_history['created_events']:
        for sub_event in event['sub_events']:
            sub_event['completed'] = False
    save_event_history(updated_history)
    st.experimental_rerun()

def toggle_completion(service, event_id, sub_event_id):
    history = get_event_history()
    for event in history['created_events']:
        if event['id'] == event_id:
            for sub_event in event['sub_events']:
                if sub_event['id'] == sub_event_id:
                    sub_event['completed'] = not sub_event['completed']
                    # Update Google Calendar event
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
                    st.experimental_rerun()
                    return

def render_progress_circle(event):
    total_sub_events = len(event['sub_events'])
    completed_sub_events = sum(1 for sub_event in event['sub_events'] if sub_event['completed'])
    
    circle_parts = []
    for i in range(total_sub_events):
        if i < completed_sub_events:
            circle_parts.append('<span style="color:green;">&#9679;</span>')  # filled circle part
        else:
            circle_parts.append('<span style="color:lightgrey;">&#9675;</span>')  # unfilled circle part
    
    return ' '.join(circle_parts)

# Other imports and code...

# Sorting function
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

    history = get_event_history()
    updated_history = verify_events(service, history)
    if history != updated_history:
        save_event_history(updated_history)
        st.experimental_rerun()

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
                        st.experimental_rerun()  # Refresh the app to show the updated event list
                    except googleapiclient.errors.HttpError as error:
                        st.error(f"An error occurred while deleting event {event_id}: {error}")

    # Date picker for existing events preview
    st.sidebar.title('Existing Events')
    selected_date = st.sidebar.date_input("Select a date to view existing events:")

    # Fetch existing events for the selected date
    time_min = datetime.datetime.combine(selected_date, datetime.time.min).isoformat() + 'Z'
    time_max = datetime.datetime.combine(selected_date, datetime.time.max).isoformat() + 'Z'
    existing_events = get_existing_events(service, time_min=time_min, time_max=time_max)

    if existing_events:
        for event in existing_events:
            st.sidebar.write(f"{event['start'].get('dateTime', event['start'].get('date'))}: {event['summary']}")
    else:
        st.sidebar.write("No events found for the selected date.")

    st.sidebar.button('Reset Progress', on_click=reset_progress)

    with st.form(key='event_form', clear_on_submit=True):
        st.subheader('Create New Study Event')
        event_title = st.text_input("Title")
        subject = st.text_input("Subject")
        start_date = st.date_input("Start Date")
        start_time = st.time_input("Start Time")
        duration_hours = st.number_input("Duration (hours)", min_value=1, max_value=12, value=1)
        duration_minutes = st.number_input("Duration (minutes)", min_value=0, max_value=59, value=0)
        repeat_frequency = st.number_input("Repeat Frequency (days)", min_value=1, max_value=365, value=7)
        total_repeats = st.number_input("Total Repeats", min_value=1, max_value=52, value=10)
        submit_button = st.form_submit_button(label='Create Event')

        if submit_button:
            if not event_title or not subject:
                st.warning("Please fill out all required fields.")
            else:
                start_dt = datetime.datetime.combine(start_date, start_time)
                sri_lanka_tz = pytz.timezone('Asia/Colombo')
                start_dt = sri_lanka_tz.localize(start_dt)

                end_dt = start_dt + datetime.timedelta(hours=duration_hours, minutes=duration_minutes)

                sub_events = []
                for i in range(total_repeats):
                    event_start = start_dt + datetime.timedelta(days=i * repeat_frequency)
                    event_end = end_dt + datetime.timedelta(days=i * repeat_frequency)
                    event = {
                        'summary': f"{event_title} (Session {i + 1})",
                        'start': {
                            'dateTime': event_start.isoformat(),
                            'timeZone': 'Asia/Colombo',
                        },
                        'end': {
                            'dateTime': event_end.isoformat(),
                            'timeZone': 'Asia/Colombo',
                        },
                        'colorId': get_color_id(subject),
                    }
                    try:
                        created_event = service.events().insert(calendarId='primary', body=event).execute()
                        sub_events.append({
                            'id': created_event['id'],
                            'name': f"{event_title} (Session {i + 1})",
                            'completed': False
                        })
                    except googleapiclient.errors.HttpError as error:
                        st.error(f"An error occurred while creating event {i + 1}: {error}")

                event_data = {
                    'id': sub_events[0]['id'],  # Using the first sub-event's ID as the main event ID
                    'title': event_title,
                    'subject': subject,
                    'sub_events': sub_events,
                }

                updated_history['created_events'].append(event_data)
                save_event_history(updated_history)
                st.success(f"Event '{event_title}' created successfully with {total_repeats} sessions.")

if __name__ == '__main__':
    main()
