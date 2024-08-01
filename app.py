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

def initialize_event_history():
    if 'event_history' not in st.session_state:
        st.session_state.event_history = {'created_events': [], 'completed_events': [], 'missed_events': []}
    return st.session_state.event_history

def save_event_history(history):
    st.session_state.event_history = history

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
                <div style="background-color:#{color_id}; padding: 10px; border-radius: 5px;">
                    <h4>{event_summary}</h4>
                    <p><b>Description:</b>{event_description}</p>
                    <p><b>Start:</b> {event_start.strftime('%Y-%m-%d %H:%M')}</p>
                    <p><b>End:</b> {event_end.strftime('%Y-%m-%d %H:%M')}</p>
                </div>
                """, unsafe_allow_html=True
            )
            if st.button(f"Edit", key=f"edit_{event['id']}"):
                # Edit event logic
                pass
            if st.button(f"Delete", key=f"delete_{event['id']}"):
                try:
                    service.events().delete(calendarId='primary', eventId=event['id']).execute()
                    st.success(f"Event deleted successfully.")
                    st.experimental_rerun()  # Refresh the app to show the updated event list
                except googleapiclient.errors.HttpError as error:
                    st.error(f"An error occurred while deleting event {event['id']}: {error}")

    subjects = ['Physics', 'Chemistry', 'Combined Maths']

    # Initialize session state for form inputs if not already present
    if 'event_date' not in st.session_state:
        st.session_state.event_date = datetime.date.today()
    if 'event_time' not in st.session_state:
        st.session_state.event_time = datetime.time(9, 0)
    if 'study_duration' not in st.session_state:
        st.session_state.study_duration = 60
    if 'event_subject' not in st.session_state:
        st.session_state.event_subject = subjects[0]
    if 'event_description' not in st.session_state:
        st.session_state.event_description = ""

    # Get event details from the user using Streamlit widgets
    st.session_state.event_date = st.date_input("Enter the date you first studied the topic:", value=st.session_state.event_date)
    st.session_state.event_time = st.time_input("Enter the time you first studied the topic:", value=st.session_state.event_time)
    st.session_state.study_duration = st.number_input("Enter the duration of your study session (in minutes):", min_value=1, value=st.session_state.study_duration)
    
    # Dropdown for subjects
    st.session_state.event_subject = st.selectbox("Select your subject:", subjects, index=subjects.index(st.session_state.event_subject))
    
    # Text area for event description
    st.session_state.event_description = st.text_area("Enter a description for the study session:", value=st.session_state.event_description)
    
    # List of intervals for spaced repetition
    intervals = [1, 7, 16, 30, 90, 180, 365]
    interval_actions = {
        1: 'Review notes',
        7: 'Revise thoroughly',
        16: 'Solve problems',
        30: 'Revise again',
        90: 'Test yourself',
        180: 'Deep review',
        365: 'Final review'
    }
    
    if st.button("Create Events"):
        # Validation checks
        if not st.session_state.event_date:
            st.error("Date is required.")
        elif not st.session_state.event_time:
            st.error("Time is required.")
        elif not st.session_state.study_duration:
            st.error("Study duration is required.")
        elif not st.session_state.event_subject:
            st.error("Subject is required.")
        elif not st.session_state.event_description:
            st.error("Description is required.")
        else:
            event_datetime = datetime.datetime.combine(st.session_state.event_date, st.session_state.event_time)
            sri_lanka_tz = pytz.timezone('Asia/Colombo')
            event_datetime_sri_lanka = sri_lanka_tz.localize(event_datetime)
        
            success = True
            sub_events = []

            for interval in intervals:
                action = interval_actions[interval]
                event_title = f"{st.session_state.event_subject}: {action}"
                event_datetime_interval = event_datetime_sri_lanka + datetime.timedelta(days=interval)
                event_end_interval = event_datetime_interval + datetime.timedelta(minutes=st.session_state.study_duration)
        
                # Check if the final event exceeds August 2025 and adjust if necessary
                if interval == 365 and event_datetime_interval > datetime.datetime(2025, 8, 31, tzinfo=sri_lanka_tz):
                    event_datetime_interval = datetime.datetime(2025, 8, 31, 23, 59, tzinfo=sri_lanka_tz)
                    event_end_interval = event_datetime_interval + datetime.timedelta(minutes=st.session_state.study_duration)

                event_body = {
                    'summary': event_title,
                    'description': st.session_state.event_description,
                    'start': {
                        'dateTime': event_datetime_interval.isoformat(),
                        'timeZone': 'Asia/Colombo',
                 },
                    'end': {
                        'dateTime': event_end_interval.isoformat(),
                        'timeZone': 'Asia/Colombo',
                    },
                    'colorId': get_color_id(st.session_state.event_subject),
                    }

                try:
                    created_event = service.events().insert(calendarId='primary', body=event_body).execute()
                    sub_events.append({'id': created_event['id'], 'name': event_title, 'completed': False})
                except googleapiclient.errors.HttpError as error:
                    st.error(f"An error occurred while creating the event for interval {interval} days: {error}")
                    success = False
                    break

            if success:
                main_event = {
                    'id': created_event['id'],
                    'date': event_datetime_sri_lanka.isoformat(),
                    'title': st.session_state.event_description,
                    'sub_events': sub_events
                }
                updated_history['created_events'].append(main_event)
                save_event_history(updated_history)
                st.success('All events created successfully!')
                st.balloons()

                # Clear the form after creating events
            st.session_state.event_date = datetime.date.today()
            st.session_state.event_time = datetime.time(9, 0)
            st.session_state.study_duration = 60
            st.session_state.event_subject = subjects[0]
            st.session_state.event_description = ""

            st.experimental_rerun()

# Run the app
if __name__ == '__main__':
    main()