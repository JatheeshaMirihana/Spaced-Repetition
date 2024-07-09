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
            circle_parts.append('<span style="font-size: 1.5em; color:green;">&#9679;</span>')  # filled circle part
        else:
            circle_parts.append('<span style="font-size: 1.5em; color:lightgrey;">&#9675;</span>')  # unfilled circle part
    
    return ' '.join(circle_parts)

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

    for event in updated_history['created_events']:
        event_id = event['id']
        event_title = event['title']
        if len(event_title) > 20:
            event_title = event_title[:17] + "..."
        
        st.sidebar.markdown(f"**{event_title}**: {render_progress_circle(event)}", unsafe_allow_html=True)
        
        with st.sidebar.expander(f"Details for {event_title}"):
            col1, col2 = st.columns([8, 1])
            with col1:
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
        event_id = event['id']
        event_summary = event.get('summary', 'No Title')
        event_start = event['start'].get('dateTime', event['start'].get('date'))
        event_start = isoparse(event_start)
        event_start_str = convert_to_sri_lanka_time(event_start).strftime('%Y-%m-%d %H:%M')

        st.sidebar.markdown(f"**{event_summary}** ({event_start_str})")
        if st.sidebar.button(f"Delete", key=f"delete_{event_id}"):
            try:
                service.events().delete(calendarId='primary', eventId=event_id).execute()
                st.experimental_rerun()  # Refresh the app to show the updated event list
            except googleapiclient.errors.HttpError as error:
                st.error(f"An error occurred while deleting event {event_id}: {error}")

    # User inputs for event creation
    st.subheader('Create New Spaced Repetition Event')
    title = st.text_input("Title of the event")
    subject = st.selectbox('Subject', ['Physics', 'Chemistry', 'Combined Maths', 'Other'])
    num_days = st.number_input("Number of days for the event", min_value=1, max_value=365)
    start_date = st.date_input("Start date", datetime.date.today())
    start_time = st.time_input("Start time", datetime.time(8, 0))

    if st.button('Create Event'):
        try:
            event_history = get_event_history()
            new_event_id = f"event_{len(event_history['created_events']) + 1}"

            # Spaced repetition intervals in days
            intervals = [1, 7, 16, 30, 90, 180, 365]
            actions = ['Review notes', 'Revise thoroughly', 'Practice questions', 'Mock test', 'Revise key points', 'Group discussion', 'Final review']
            start_datetime = datetime.datetime.combine(start_date, start_time)
            event_timezone = 'Asia/Colombo'

            event = {
                'id': new_event_id,
                'title': title,
                'subject': subject,
                'sub_events': []
            }

            for i, interval in enumerate(intervals):
                action = actions[i]
                event_datetime = start_datetime + datetime.timedelta(days=interval)
                event_id = f"{new_event_id}_sub_{i + 1}"
                sub_event = {
                    'id': event_id,
                    'name': f"{title} - {action}",
                    'completed': False
                }
                event['sub_events'].append(sub_event)

                event_body = {
                    'summary': sub_event['name'],
                    'start': {
                        'dateTime': event_datetime.isoformat(),
                        'timeZone': event_timezone,
                    },
                    'end': {
                        'dateTime': (event_datetime + datetime.timedelta(hours=1)).isoformat(),
                        'timeZone': event_timezone,
                    },
                    'colorId': get_color_id(subject),
                    'reminders': {
                        'useDefault': False,
                        'overrides': [
                            {'method': 'popup', 'minutes': 24 * 60},  # reminder 1 day before
                        ],
                    },
                }

                try:
                    created_event = service.events().insert(calendarId='primary', body=event_body).execute()
                    sub_event['id'] = created_event['id']
                except googleapiclient.errors.HttpError as error:
                    st.error(f"An error occurred while creating event: {error}")
                    return

            event_history['created_events'].append(event)
            save_event_history(event_history)
            st.success("Event created successfully!")

        except Exception as e:
            st.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
