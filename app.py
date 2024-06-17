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
from streamlit_autorefresh import st_autorefresh

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

def get_credentials():
    creds = None
    try:
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                raise google.auth.exceptions.RefreshError("Manual reauthentication required. Please perform the authentication on a local machine and transfer the token.json file.")
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

def check_conflicts(new_event_start, new_event_end, existing_events):
    for event in existing_events:
        existing_start = datetime.datetime.fromisoformat(event['start']['dateTime'][:-1])
        existing_end = datetime.datetime.fromisoformat(event['end']['dateTime'][:-1])
        if new_event_start < existing_end and new_event_end > existing_start:
            return True
    return False

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
        
        # Fetch existing events and check for conflicts
        existing_events = get_existing_events(service, time_min=event_datetime_sri_lanka.isoformat(), time_max=event_end.isoformat())

        if check_conflicts(event_datetime_sri_lanka, event_end, existing_events):
            st.warning("There are conflicting events during this time. You may need to adjust your event time.")
        else:
            st.success("No conflicts detected. You can schedule this event.")

    if st.button('Schedule Event'):
        if not event_subject or not event_description:
            st.error("Please fill in all the fields to schedule an event.")
        else:
            with st.spinner('Creating events...'):
                color_id = get_color_id(event_subject)
                intervals = [1, 7, 16, 35, 90, 180, 365]
                success = True

                for interval in intervals:
                    event_datetime_interval = event_datetime_sri_lanka + datetime.timedelta(days=interval)
                    event_end_interval = event_datetime_interval + datetime.timedelta(minutes=study_duration)

                    # Fetch existing events for the interval and check for conflicts
                    existing_events_interval = get_existing_events(service, time_min=event_datetime_interval.isoformat(), time_max=event_end_interval.isoformat())

                    if check_conflicts(event_datetime_interval, event_end_interval, existing_events_interval):
                        st.warning(f"Conflict detected for the interval {interval} days. Skipping this event.")
                        success = False
                        continue

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

                    try:
                        service.events().insert(calendarId='primary', body=new_event).execute()
                    except googleapiclient.errors.HttpError as error:
                        st.error(f"An error occurred while creating an event: {error}")
                        success = False

                if success:
                    st.success('Events Created Successfully ✔')
                else:
                    st.warning('Some events were not created due to conflicts.')

    # Set the interval for rerun
    st_autorefresh(interval=10 * 1000)  # Refresh every 10 seconds

if __name__ == '__main__':
    main()
