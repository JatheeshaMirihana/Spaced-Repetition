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

def parse_event_time(event_time):
    try:
        if 'dateTime' in event_time:
            return datetime.datetime.fromisoformat(event_time['dateTime'][:-1])
        elif 'date' in event_time:
            return datetime.datetime.fromisoformat(event_time['date'])
        else:
            raise ValueError("Unknown time format in event")
    except Exception as e:
        st.error(f"Error parsing event time: {e}")
        raise

def check_conflicts(new_event_start, new_event_end, existing_events):
    for event in existing_events:
        try:
            existing_start = parse_event_time(event['start'])
            existing_end = parse_event_time(event['end'])
            if 'date' in event['start']:
                existing_end += datetime.timedelta(days=1)  # all-day event ends at the start of the next day

            if new_event_start < existing_end and new_event_end > existing_start:
                return True
        except KeyError as e:
            st.error(f"KeyError in event: {e}")
            continue
        except ValueError as e:
            st.error(f"ValueError in event: {e}")
            continue
    return False

def get_free_time_slots(existing_events, day_start, day_end):
    free_slots = []
    current_time = day_start

    for event in existing_events:
        existing_start = parse_event_time(event['start'])
        existing_end = parse_event_time(event['end'])
        if 'date' in event['start']:
            existing_end += datetime.timedelta(days=1)  # all-day event ends at the start of the next day

        if current_time < existing_start:
            free_slots.append((current_time, existing_start))
        current_time = max(current_time, existing_end)
    
    if current_time < day_end:
        free_slots.append((current_time, day_end))
    
    return free_slots

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
                overlapping_intervals = []

                for interval in intervals:
                    event_datetime_interval = event_datetime_sri_lanka + datetime.timedelta(days=interval)
                    event_end_interval = event_datetime_interval + datetime.timedelta(minutes=study_duration)

                    # Fetch existing events for the interval and check for conflicts
                    existing_events_interval = get_existing_events(service, time_min=event_datetime_interval.isoformat(), time_max=event_end_interval.isoformat())

                    if check_conflicts(event_datetime_interval, event_end_interval, existing_events_interval):
                        overlapping_intervals.append(interval)
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
                    for interval in overlapping_intervals:
                        interval_date = event_datetime_sri_lanka + datetime.timedelta(days=interval)
                        day_start = interval_date.replace(hour=0, minute=0, second=0, microsecond=0)
                        day_end = interval_date.replace(hour=23, minute=59, second=59, microsecond=999999)
                        existing_events_interval = get_existing_events(service, time_min=day_start.isoformat(), time_max=day_end.isoformat())
                        free_slots = get_free_time_slots(existing_events_interval, day_start, day_end)

                        st.info(f"Suggestions for free time slots on {interval_date.strftime('%Y-%m-%d')} for the interval {interval} days:")
                        for start, end in free_slots:
                            st.write(f"From {start.strftime('%H:%M')} to {end.strftime('%H:%M')}")

    # Set the interval for rerun
    st_autorefresh(interval=10 * 1000)  # Refresh every 10 seconds

if __name__ == '__main__':
    main()
