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

# Create new spaced-repetition events
def create_events(service, subject, start_time, duration, description):
    intervals = [1, 3, 7, 14, 30, 60, 90]  # Spaced repetition intervals in days
    event_ids = []
    
    for i, interval in enumerate(intervals):
        event_time = start_time + datetime.timedelta(days=interval)
        event = {
            'summary': f'{subject} Study Session - {i+1}',
            'description': description,
            'start': {
                'dateTime': event_time.isoformat(),
                'timeZone': 'Asia/Colombo',
            },
            'end': {
                'dateTime': (event_time + datetime.timedelta(minutes=duration)).isoformat(),
                'timeZone': 'Asia/Colombo',
            },
            'colorId': get_color_id(subject),
        }
        
        try:
            created_event = service.events().insert(calendarId='primary', body=event).execute()
            event_ids.append(created_event['id'])
            st.success(f"Event {i+1} created: {created_event['htmlLink']}")
        except googleapiclient.errors.HttpError as error:
            st.error(f"An error occurred: {error}")
            break
    
    return event_ids

# Retrieve existing events from the Google Calendar
def get_existing_events(service, calendar_id='primary', time_min=None, time_max=None):
    try:
        events_result = service.events().list(calendarId=calendar_id, timeMin=time_min, timeMax=time_max, singleEvents=True, orderBy='startTime').execute()
        return events_result.get('items', [])
    except googleapiclient.errors.HttpError as error:
        st.error(f"An error occurred while fetching events: {error}")
        return []

# Main function to display the form and allow user to create events
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

    st.header("Schedule New Study Sessions")

    with st.form(key='event_form'):
        subject = st.selectbox("Subject", ["Physics", "Combined Maths", "Chemistry"])
        start_date = st.date_input("Start Date", datetime.date.today())
        start_time = st.time_input("Start Time", datetime.datetime.now().time())
        duration = st.number_input("Duration (in minutes)", min_value=1, max_value=180, value=60)
        description = st.text_area("Description", "Enter details about your study session")
        
        submit_button = st.form_submit_button(label='Schedule Events')

        if submit_button:
            start_datetime = datetime.datetime.combine(start_date, start_time)
            start_datetime = convert_to_sri_lanka_time(start_datetime)
            create_events(service, subject, start_datetime, duration, description)

if __name__ == '__main__':
    main()
