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

    # Progress bar
    total_events = sum(len(event['sub_events']) for event in updated_history['created_events'])
    completed_events = sum(1 for event in updated_history['created_events'] for sub_event in event['sub_events'] if sub_event['completed'])
    progress = (completed_events / total_events) * 100 if total_events > 0 else 0
    st.progress(progress / 100)
    st.write(f"{progress:.2f}% complete")

    # Right Sidebar for Progress Tracker
    st.sidebar.title('Your Progress')

    if 'event_checkboxes' not in st.session_state:
        st.session_state.event_checkboxes = {}

    def toggle_completion(event_id, sub_event_id):
        for event in updated_history['created_events']:
            if event['id'] == event_id:
                for sub_event in event['sub_events']:
                    if sub_event['id'] == sub_event_id:
                        sub_event['completed'] = not sub_event['completed']
                        sub_event['name'] = f"Completed: {sub_event['name']}" if sub_event['completed'] else sub_event['name'].replace("Completed: ", "")
                        save_event_history(updated_history)
                        st.experimental_rerun()
                        return

    for event in updated_history['created_events']:
        event_id = event['id']
        event_title = event['title']
        if len(event_title) > 20:
            event_title = event_title[:17] + "..."
        with st.sidebar.expander(f"{event_title}"):
            col1, col2 = st.columns([8, 1])
            with col1:
                all_completed = all(sub_event['completed'] for sub_event in event['sub_events'])
                st.markdown(f"<div style='border: 2px solid #00BFFF; border-radius: 50%; padding: 5px; width: 20px; height: 20px; text-align: center;'>{'✓' if all_completed else ''}</div>", unsafe_allow_html=True)
                for sub_event in event['sub_events']:
                    sub_event_id = sub_event['id']
                    is_completed = sub_event['completed']
                    event_name = sub_event['name']
                    if is_completed:
                        event_name = f"Completed: {event_name}"
                    st.checkbox(event_name, value=is_completed, key=f"cb_{sub_event_id}", on_change=toggle_completion, args=(event_id, sub_event_id))
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

    # Display existing events with edit/delete options in the sidebar
    for event in existing_events:
        event_start = isoparse(event['start']['dateTime'])
        event_end = isoparse(event['end']['dateTime'])
        event_summary = event.get('summary', 'No Summary')
        event_description = event.get('description', 'No Description')
        color_id = get_color_id(event_summary.split(':')[0])
        with st.sidebar.container():
            st.markdown(
                f"""
                <div style="background-color:#{color_id}; padding: 10px; margin-bottom: 10px;">
                Name: {event_summary}<br>
                Date: {event_start.strftime('%Y-%m-%d')}<br>
                Duration: {event_start.strftime('%H:%M')} to {event_end.strftime('%H:%M')}<br>
                Description: {event_description}
                </div>
                """,
                unsafe_allow_html=True
            )
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button(f"📝 Edit", key=f"edit_{event['id']}"):
                    st.write("Editing not implemented yet.")
            with col2:
                if st.button(f"🗑️ Delete", key=f"delete_{event['id']}"):
                    try:
                        service.events().delete(calendarId='primary', eventId=event['id']).execute()
                        st.experimental_rerun()  # Refresh the app to show the updated event list
                    except googleapiclient.errors.HttpError as error:
                        st.error(f"An error occurred: {error}")

    # Form to create new event
    st.header('Create a New Event')
    event_date = st.date_input("Select the date of the event:", value=datetime.datetime.today(), min_value=datetime.datetime.today())
    event_time = st.time_input("Select the time of the event:")
    event_summary = st.text_input("Enter the title of the event:", value="", help="This field is required.")
    event_description = st.text_area("Enter a description of the event:", value="", help="This field is required.")
    event_duration = st.number_input("Enter the duration of the event (in hours):", min_value=1, step=1, help="This field is required.")
    event_subject = st.text_input("Enter the subject of the event:", value="", help="This field is required.")

    if st.button("Create Event"):
        if not event_summary or not event_description or not event_subject:
            st.error("All fields are required.")
        else:
            start_datetime = datetime.datetime.combine(event_date, event_time)
            end_datetime = start_datetime + datetime.timedelta(hours=event_duration)
            event_color_id = get_color_id(event_subject)
            event = {
                'summary': event_summary,
                'description': event_description,
                'start': {'dateTime': start_datetime.isoformat(), 'timeZone': 'Asia/Colombo'},
                'end': {'dateTime': end_datetime.isoformat(), 'timeZone': 'Asia/Colombo'},
                'colorId': event_color_id
            }

            try:
                created_event = service.events().insert(calendarId='primary', body=event).execute()
                st.success(f"Event created: {created_event['htmlLink']}")
                st.balloons()
                # Add the new event to the history
                new_event = {
                    'id': created_event['id'],
                    'title': event_summary,
                    'sub_events': [{'id': created_event['id'], 'name': event_summary, 'completed': False}]
                }
                updated_history['created_events'].append(new_event)
                save_event_history(updated_history)
                st.experimental_rerun()
            except googleapiclient.errors.HttpError as error:
                st.error(f"An error occurred: {error}")

if __name__ == '__main__':
    main()
