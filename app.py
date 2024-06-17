from __future__ import print_function
import datetime
import os.path
import pytz
import streamlit as st
import time
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import googleapiclient.errors

# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar.events.readonly', 'https://www.googleapis.com/auth/calendar.events']

@st.cache_data
def get_color_id(subject):
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
def convert_to_sri_lanka_time(dt):
    sri_lanka_tz = pytz.timezone('Asia/Colombo')
    return dt.astimezone(sri_lanka_tz)

@st.cache_data
def get_credentials():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def get_existing_events(service, calendar_id='primary', time_min=None, time_max=None):
    events_result = service.events().list(calendarId=calendar_id, timeMin=time_min, timeMax=time_max, singleEvents=True, orderBy='startTime').execute()
    return events_result.get('items', [])

def check_conflicts(new_event_start, new_event_end, existing_events):
    for event in existing_events:
        existing_start = datetime.datetime.fromisoformat(event['start']['dateTime'][:-1])
        existing_end = datetime.datetime.fromisoformat(event['end']['dateTime'][:-1])
        if new_event_start < existing_end and new_event_end > existing_start:
            return True
    return False

def main():
    creds = get_credentials()

    try:
        service = build('calendar', 'v3', credentials=creds)
    except googleapiclient.errors.HttpError as error:
        st.error(f"An error occurred: {error}")
        return

    st.title('Google Calendar Event Scheduler')

    # Get event details from the user using Streamlit widgets
    event_date = st.date_input("Enter the date you first studied the topic:")
    event_time = st.time_input("Enter the time you first studied the topic:")
    study_duration = st.number_input("Enter the duration of your study session (in minutes):", min_value=1)
    event_subject = st.selectbox("Select the subject of the event:", ["Physics", "Chemistry", "Combined Maths", "Other"])
    event_description = st.text_area("Enter the description of the event:")

    if event_date and event_time:
        event_datetime = datetime.datetime.combine(event_date, event_time)
        event_datetime = pytz.timezone('Asia/Colombo').localize(event_datetime)
        event_datetime_sri_lanka = convert_to_sri_lanka_time(event_datetime)
        event_end = event_datetime_sri_lanka + datetime.timedelta(minutes=study_duration)
        existing_events = get_existing_events(service, time_min=event_datetime_sri_lanka.isoformat(), time_max=event_end.isoformat())

        if check_conflicts(event_datetime_sri_lanka, event_end, existing_events):
            st.warning("There are conflicting events during this time. You may need to adjust your event time.")

    if st.button('Schedule Event'):
        if not event_subject or not event_description:
            st.error("Please fill in all the fields to schedule an event.")
        else:
            with st.spinner('Creating events...'):
                color_id = get_color_id(event_subject)
                intervals = [1, 7, 16, 35, 90, 180, 365]

                for interval in intervals:
                    event_datetime_interval = event_datetime_sri_lanka + datetime.timedelta(days=interval)
                    event_end_interval = event_datetime_interval + datetime.timedelta(minutes=study_duration)

                    new_event = {
                        'summary': f"{event_subject} - Review",
                        'description': event_description,
                        'start': {
                            'dateTime': event_datetime_interval.isoformat(),
                            'timeZone': 'Asia/Colombo',
                        },
                        'end': {
                            'dateTime': event_end_interval.isoformat(),
                            'timeZone': 'Asia/Colombo',
                        },
                        'colorId': color_id,
                    }

                    service.events().insert(calendarId='primary', body=new_event).execute()
                    time.sleep(0.2)  # Simulating some delay for each event creation
                st.success('Events Created Successfully ✔')

if __name__ == '__main__':
    main()
