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
                        
                        # Update the event title and color on Google Calendar
                        try:
                            # Fetch the existing event details
                            existing_event = service.events().get(calendarId='primary', eventId=sub_event['id']).execute()
                            
                            # Update the title and color based on completion status
                            updated_event = {
                                'summary': f"Completed: {existing_event['summary']}" if sub_event['completed'] else existing_event['summary'].replace("Completed: ", ""),
                                'colorId': '8' if sub_event['completed'] else existing_event.get('colorId', '1'),  # Graphite if completed, otherwise default or previous color
                            }
                            
                            # Update the event on Google Calendar
                            service.events().patch(calendarId='primary', eventId=sub_event['id'], body=updated_event).execute()
                            
                        except googleapiclient.errors.HttpError as error:
                            st.error(f"An error occurred while updating the event {sub_event_id}: {error}")
                        
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
                for sub_event in event['sub_events']:
                    sub_event_id = sub_event['id']
                    is_completed = sub_event['completed']
                    event_name = sub_event['name']
                    if is_completed:
                        event_name = f"~~{event_name}~~"
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
            col1, col2 = st.sidebar.columns([1, 1])
            with col1:
                if st.button(f"Edit", key=f"edit_{event['id']}"):
                    st.warning("Edit functionality not implemented yet.")
            with col2:
                if st.button(f"Delete", key=f"delete_{event['id']}"):
                    try:
                        service.events().delete(calendarId='primary', eventId=event['id']).execute()
                        st.experimental_rerun()
                    except googleapiclient.errors.HttpError as error:
                        st.error(f"An error occurred while deleting the event: {error}")

    st.sidebar.button("Reset Progress", on_click=reset_progress)

    # Main Page for Event Creation
    st.header('Create a New Event')

    title = st.text_input('Event Title')
    date = st.date_input('Event Date')
    start_time = st.time_input('Start Time')
    end_time = st.time_input('End Time')
    description = st.text_area('Description')
    location = st.text_input('Location')
    subject = st.selectbox('Subject', ['Physics', 'Chemistry', 'Combined Maths', 'Other'])
    sub_events_count = st.number_input('Number of sub-events', min_value=1, step=1, value=1)

    sub_events = []
    for i in range(sub_events_count):
        sub_event_title = st.text_input(f'Sub-event {i + 1} Title')
        sub_event_duration = st.number_input(f'Sub-event {i + 1} Duration (minutes)', min_value=1, step=1, value=30)
        sub_events.append({
            'title': sub_event_title,
            'duration': sub_event_duration,
        })

    if st.button('Create Event'):
        try:
            sri_lanka_tz = pytz.timezone('Asia/Colombo')
            start_datetime = sri_lanka_tz.localize(datetime.datetime.combine(date, start_time))
            end_datetime = sri_lanka_tz.localize(datetime.datetime.combine(date, end_time))

            event_data = {
                'summary': title,
                'location': location,
                'description': description,
                'start': {
                    'dateTime': start_datetime.isoformat(),
                    'timeZone': 'Asia/Colombo',
                },
                'end': {
                    'dateTime': end_datetime.isoformat(),
                    'timeZone': 'Asia/Colombo',
                },
                'colorId': get_color_id(subject),
            }

            main_event = service.events().insert(calendarId='primary', body=event_data).execute()
            main_event_id = main_event['id']

            event_history = get_event_history()

            created_sub_events = []
            current_start = start_datetime

            for sub_event in sub_events:
                sub_event_end = current_start + datetime.timedelta(minutes=sub_event['duration'])
                sub_event_data = {
                    'summary': f"{subject}: {sub_event['title']}",
                    'location': location,
                    'description': description,
                    'start': {
                        'dateTime': current_start.isoformat(),
                        'timeZone': 'Asia/Colombo',
                    },
                    'end': {
                        'dateTime': sub_event_end.isoformat(),
                        'timeZone': 'Asia/Colombo',
                    },
                    'colorId': get_color_id(subject),
                }

                created_sub_event = service.events().insert(calendarId='primary', body=sub_event_data).execute()
                created_sub_events.append({
                    'id': created_sub_event['id'],
                    'name': sub_event['title'],
                    'completed': False,
                })

                current_start = sub_event_end

            event_history['created_events'].append({
                'id': main_event_id,
                'title': title,
                'sub_events': created_sub_events,
            })

            save_event_history(event_history)
            st.success('Event created successfully!')

        except googleapiclient.errors.HttpError as error:
            st.error(f"An error occurred: {error}")

if __name__ == '__main__':
    main()
