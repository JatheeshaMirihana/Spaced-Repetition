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

SCOPES = ['https://www.googleapis.com/auth/calendar.events.readonly', 
          'https://www.googleapis.com/auth/calendar.events', 
          'https://www.googleapis.com/auth/drive.file']

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

def upload_history_to_drive(service, history):
    try:
        file_metadata = {'name': 'history.json', 'mimeType': 'application/json'}
        media = googleapiclient.http.MediaInMemoryUpload(json.dumps(history), mimetype='application/json')
        
        response = service.files().list(q="name='history.json'", fields='files(id)').execute()
        files = response.get('files', [])
        
        if files:
            file_id = files[0]['id']
            service.files().update(fileId=file_id, media_body=media).execute()
        else:
            service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    except googleapiclient.errors.HttpError as error:
        st.error(f"An error occurred while uploading history to Google Drive: {error}")

def download_history_from_drive(service):
    try:
        response = service.files().list(q="name='history.json'", fields='files(id)').execute()
        files = response.get('files', [])
        
        if files:
            file_id = files[0]['id']
            request = service.files().get_media(fileId=file_id)
            history_data = request.execute()
            return json.loads(history_data)
        else:
            return {'created_events': [], 'completed_events': [], 'missed_events': []}
    except googleapiclient.errors.HttpError as error:
        st.error(f"An error occurred while downloading history from Google Drive: {error}")
        return {'created_events': [], 'completed_events': [], 'missed_events': []}

def get_event_history(service):
    return download_history_from_drive(service)

def save_event_history(service, history):
    upload_history_to_drive(service, history)

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

def reset_progress(service):
    updated_history = get_event_history(service)
    for event in updated_history['created_events']:
        for sub_event in event['sub_events']:
            sub_event['completed'] = False
    save_event_history(service, updated_history)
    st.experimental_rerun()

def toggle_completion(service, event_id, sub_event_id):
    history = get_event_history(service)
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
                    save_event_history(service, history)
                    st.experimental_rerun()
                    return

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
        drive_service = build('drive', 'v3', credentials=creds)
    except googleapiclient.errors.HttpError as error:
        st.error(f"An error occurred: {error}")
        return

    st.title('Google Calendar Event Scheduler')

    history = get_event_history(drive_service)
    updated_history = verify_events(service, history)
    if history != updated_history:
        save_event_history(drive_service, updated_history)
        st.experimental_rerun()

    st.sidebar.title('Your Progress')
    sort_option = st.sidebar.selectbox("Sort by:", ["Title", "Date", "Completion"], index=0)

    if 'event_checkboxes' not in st.session_state:
        st.session_state.event_checkboxes = {}

    sorted_events = sort_events(updated_history['created_events'], sort_option)

    for event in sorted_events:
        event_id = event['id']
        event_title = event['title']
        if len(event_title) > 20:
            event_title = event_title[:20] + "..."
        st.sidebar.write(event_title)
        st.sidebar.write(render_progress_circle(event))
        for sub_event in event['sub_events']:
            sub_event_id = sub_event['id']
            checkbox_key = f"{event_id}_{sub_event_id}"
            checkbox_label = f"{sub_event['title']} ({sub_event['start'].split('T')[0]})"
            is_checked = sub_event['completed']
            st.session_state.event_checkboxes[checkbox_key] = st.sidebar.checkbox(
                checkbox_label, value=is_checked, key=checkbox_key,
                on_change=toggle_completion, args=(drive_service, event_id, sub_event_id)
            )

    if st.sidebar.button("Reset Progress"):
        reset_progress(drive_service)

    # Original User Inputs
    event_title = st.text_input("Enter the event title")
    subject = st.selectbox("Select subject", ['Physics', 'Chemistry', 'Combined Maths', 'Other'])
    description = st.text_area("Enter the event description")
    start = st.date_input("Start date")
    end = st.date_input("End date")
    start_time = st.time_input("Start time")
    end_time = st.time_input("End time")
    num_sub_events = st.number_input("Number of Sub Events", min_value=1, max_value=10, value=1)

    if st.button("Create Event"):
        event_id = f"custom-{datetime.datetime.now().timestamp()}"
        sub_events = []
        for i in range(int(num_sub_events)):
            sub_event_title = f"{event_title} - Part {i+1}"
            sub_event_id = f"sub-{event_id}-{i+1}"
            sub_events.append({
                'id': sub_event_id,
                'title': sub_event_title,
                'start': f"{start}T{start_time.isoformat()}Z",
                'end': f"{end}T{end_time.isoformat()}Z",
                'completed': False
            })
        
        event = {
            'id': event_id,
            'title': event_title,
            'subject': subject,
            'description': description,
            'start': f"{start}T{start_time.isoformat()}Z",
            'end': f"{end}T{end_time.isoformat()}Z",
            'sub_events': sub_events
        }
        updated_history['created_events'].append(event)
        save_event_history(drive_service, updated_history)
        st.success("Event created successfully!")
        st.experimental_rerun()

if __name__ == "__main__":
    main()
