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
    if subject in ['physics', 'p6', 'Physics']:
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

    # Progress tracker
    total_events = len(history['created_events'])
    completed_events = len(history['completed_events'])
    missed_events = len(history['missed_events'])
    progress_percentage = (completed_events / total_events) * 100 if total_events > 0 else 0
    streak_counter = calculate_streak(history['completed_events'])

    # Display progress tracker on the right sidebar
    with st.sidebar.container():
        st.sidebar.title('Progress Tracker')
        st.sidebar.progress(progress_percentage / 100)
        st.sidebar.write(f"Completed: {completed_events}/{total_events} events")
        st.sidebar.write(f"Current streak: {streak_counter} days")
        st.sidebar.write(f"Missed events: {missed_events}")
        if st.button("Reset Progress"):
            history['completed_events'] = []
            history['missed_events'] = []
            save_event_history(history)
            st.experimental_rerun()  # Refresh the app to show the updated progress

    # Date picker for existing events preview
    selected_date = st.sidebar.date_input("Select a date to view existing events:")

    # Fetch existing events for the selected date
    time_min = datetime.datetime.combine(selected_date, datetime.time.min).isoformat() + 'Z'
    time_max = datetime.datetime.combine(selected_date, datetime.time.max).isoformat() + 'Z'
    existing_events = get_existing_events(service, time_min=time_min, time_max=time_max)

    # Display existing events with edit/delete/mark as done options in the sidebar
    st.sidebar.title('Existing Events')
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
            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                if st.button(f"Edit", key=f"edit_{event['id']}"):
                    st.warning("Edit functionality not implemented yet.")
            with col2:
                if st.button(f"Delete", key=f"delete_{event['id']}"):
                    try:
                        service.events().delete(calendarId='primary', eventId=event['id']).execute()
                        st.success(f"Event deleted successfully.")
                        st.experimental_rerun()  # Refresh the app to show the updated event list
                    except googleapiclient.errors.HttpError as error:
                        st.error(f"An error occurred while deleting event {event['id']}: {error}")
            with col3:
                if st.button(f"Done", key=f"done_{event['id']}"):
                    history['completed_events'].append({'id': event['id'], 'date': datetime.datetime.now().isoformat()})
                    save_event_history(history)
                    st.success(f"Event marked as done.")
                    st.experimental_rerun()  # Refresh the app to show the updated event list
                if st.button(f"Incomplete", key=f"incomplete_{event['id']}"):
                    try:
                        new_event = service.events().insert(calendarId='primary', body={
                            'summary': event_summary,
                            'description': event_description,
                            'start': {
                                'dateTime': (datetime.datetime.now() + datetime.timedelta(days=1)).isoformat(),
                                'timeZone': 'Asia/Colombo',
                            },
                            'end': {
                                'dateTime': (datetime.datetime.now() + datetime.timedelta(days=1, minutes=30)).isoformat(),
                                'timeZone': 'Asia/Colombo',
                            },
                            'colorId': get_color_id(event_summary.split(':')[0]),
                        }).execute()
                        history['missed_events'].append({'id': event['id'], 'date': datetime.datetime.now().isoformat()})
                        save_event_history(history)
                        st.success(f"New event created for incomplete event.")
                        st.experimental_rerun()  # Refresh the app to show the updated event list
                    except googleapiclient.errors.HttpError as error:
                        st.error(f"An error occurred while creating a new event for incomplete event {event['id']}: {error}")

    # Get event details from the user using Streamlit widgets
    event_date = st.date_input("Enter the date you first studied the topic:")
    event_time = st.time_input("Enter the time you first studied the topic:")
    study_duration = st.number_input("Enter the duration of your study session (in minutes):", min_value=1)
    
    # Dropdown for subjects
    subjects = ['Physics', 'Chemistry', 'Combined Maths']
    event_subject = st.selectbox("Select the subject of the event:", subjects)
    
    # Text area for description
    event_description = st.text_area("Enter the description of the event:")

    intervals = [1, 7, 16, 35, 90, 180, 365]  # Updated intervals
    interval_actions = {
        1: "Review notes",
        7: "Revise thoroughly",
        16: "Solve problems",
        35: "Revise again",
        90: "Test yourself",
        180: "Deep review",
        365: "Final review"
    }

    if st.button("Schedule Events"):
        event_datetime = datetime.datetime.combine(event_date, event_time)
        sri_lanka_tz = pytz.timezone('Asia/Colombo')
        event_datetime_sri_lanka = sri_lanka_tz.localize(event_datetime)
        success = True
        history = get_event_history()
    
        for interval in intervals:
            action = interval_actions[interval]
            event_title = f"{event_subject}: {action}"
            event_datetime_interval = event_datetime_sri_lanka + datetime.timedelta(days=interval)
            event_end_interval = event_datetime_interval + datetime.timedelta(minutes=study_duration)
        
        # Check if the final event exceeds August 2025 and adjust if necessary
            if interval == 365 and event_datetime_interval > datetime.datetime(2025, 8, 31, tzinfo=sri_lanka_tz):
                event_datetime_interval = datetime.datetime(2025, 8, 31, 23, 59, tzinfo=sri_lanka_tz)
                event_end_interval = event_datetime_interval + datetime.timedelta(minutes=study_duration)

            event_body = {
                'summary': event_title,
                'description': event_description,
                'start': {
                    'dateTime': event_datetime_interval.isoformat(),
                        'timeZone': 'Asia/Colombo',
                },
                'end': {
                    'dateTime': event_end_interval.isoformat(),
                    'timeZone': 'Asia/Colombo',
                },
                'colorId': get_color_id(event_subject),
        }

            try:
                created_event = service.events().insert(calendarId='primary', body=event_body).execute()
                history['created_events'].append({'id': created_event['id'], 'date': event_datetime_interval.isoformat()})
                save_event_history(history)
            except googleapiclient.errors.HttpError as error:
                st.error(f"An error occurred while creating the event for interval {interval} days: {error}")
                success = False
                break

    if success:
        st.success('All events created successfully!')
        st.balloons()
def calculate_streak(completed_events):
    streak = 0
    today = datetime.datetime.now().date()
    for event in sorted(completed_events, key=lambda x: x['date'], reverse=True):
        event_date = isoparse(event['date']).date()
        if (today - event_date).days == streak:
            streak += 1
        else:
            break
    return streak

# Run the app
if __name__ == '__main__':
    main()
