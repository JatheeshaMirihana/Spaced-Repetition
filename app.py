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
            creds = Credentials.from_authorized_user_info(json.loads(st.session_state['token']), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                st.write(st.secrets)

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

                if 'code' in st.experimental_get_query_params():
                    flow.fetch_token(code=st.experimental_get_query_params()['code'][0])
                    creds = flow.credentials
                    st.session_state['token'] = creds.to_json()

                return creds
        return creds
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
            st.session_state.event_checkboxes.pop(event['id'], None)
    for event in history['completed_events']:
        if event_exists(service, event['id']):
            updated_history['completed_events'].append(event)
    for event in history['missed_events']:
        if event_exists(service, event['id']):
            updated_history['missed_events'].append(event)
    return updated_history

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
    st.session_state['event_history'] = updated_history

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

def sort_events(events, sort_option):
    if sort_option == "Title":
        return sorted(events, key=lambda x: x['title'])
    elif sort_option == "Date":
        return sorted(events, key=lambda x: x['date'])
    elif sort_option == "Completion":
        return sorted(events, key=lambda x: sum(1 for sub_event in x['sub_events'] if sub_event['completed']), reverse=True)
    else:
        return events

def create_event(service, title, description, start_datetime, end_datetime):
    try:
        event = {
            'summary': title,
            'description': description,
            'start': {
                'dateTime': start_datetime.isoformat(),
                'timeZone': 'Asia/Colombo',
            },
            'end': {
                'dateTime': end_datetime.isoformat(),
                'timeZone': 'Asia/Colombo',
            },
        }

        event = service.events().insert(calendarId='primary', body=event).execute()
        st.success(f"Event created: {event['summary']} at {event['start']['dateTime']}")
        return event
    except googleapiclient.errors.HttpError as error:
        st.error(f"An error occurred while creating the event: {error}")
        return None

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
                    if sub_event_id not in st.session_state.event_checkboxes:
                        st.session_state.event_checkboxes[sub_event_id] = sub_event['completed']
                    if st.checkbox(sub_event['title'], key=sub_event_id, value=st.session_state.event_checkboxes[sub_event_id]):
                        if not st.session_state.event_checkboxes[sub_event_id]:
                            toggle_completion(service, event_id, sub_event_id)
                    else:
                        if st.session_state.event_checkboxes[sub_event_id]:
                            toggle_completion(service, event_id, sub_event_id)
            with col2:
                if st.button("❌", key=f"del-{event_id}"):
                    try:
                        service.events().delete(calendarId='primary', eventId=event_id).execute()
                        st.success(f"Event {event_title} deleted.")
                        updated_history['created_events'].remove(event)
                        save_event_history(updated_history)
                        st.session_state['event_history'] = updated_history
                    except googleapiclient.errors.HttpError as error:
                        st.error(f"An error occurred while deleting the event: {error}")

    # Form to create new events
    with st.form("Create Event"):
        st.subheader("Create New Event")

        event_title = st.text_input("Event Title")
        event_description = st.text_area("Event Description")
        start_date = st.date_input("Start Date", datetime.date.today())
        start_time = st.time_input("Start Time", datetime.datetime.now().time())
        end_date = st.date_input("End Date", datetime.date.today())
        end_time = st.time_input("End Time", (datetime.datetime.now() + datetime.timedelta(hours=1)).time())

        submit_button = st.form_submit_button("Create Event")

        if submit_button:
            start_datetime = datetime.datetime.combine(start_date, start_time)
            end_datetime = datetime.datetime.combine(end_date, end_time)

            event = create_event(service, event_title, event_description, start_datetime, end_datetime)

            if event:
                # Add the event to the session state and history
                new_event = {
                    'id': event['id'],
                    'title': event_title,
                    'sub_events': [{
                        'id': event['id'],
                        'title': event_title,
                        'completed': False
                    }]
                }
                updated_history['created_events'].append(new_event)
                save_event_history(updated_history)
                st.session_state['event_history'] = updated_history

    if st.sidebar.button("Reset Progress"):
        reset_progress()

if __name__ == '__main__':
    main()
