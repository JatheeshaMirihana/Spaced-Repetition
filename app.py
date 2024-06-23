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
from dateutil.parser import isoparse

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
        existing_start = isoparse(event['start']['dateTime'])
        existing_end = isoparse(event['end']['dateTime'])
        if new_event_start < existing_end and new_event_end > existing_start:
            return event
    return None

def suggest_free_times(existing_events, duration, event_datetime_sri_lanka, num_suggestions=4):
    free_times = []
    day_start = event_datetime_sri_lanka.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + datetime.timedelta(days=1)
    
    current_time = day_start
    while current_time + datetime.timedelta(minutes=duration) <= day_end:
        conflict = False
        for event in existing_events:
            event_start = isoparse(event['start']['dateTime'])
            event_end = isoparse(event['end']['dateTime'])
            if current_time < event_end and (current_time + datetime.timedelta(minutes=duration)) > event_start:
                conflict = True
                current_time = event_end
                break
        if not conflict:
            free_times.append(current_time)
            if len(free_times) >= num_suggestions:
                break
            current_time += datetime.timedelta(minutes=duration)
        else:
            current_time += datetime.timedelta(minutes=15)  # Move in 15-minute increments
    return free_times

def display_event_with_controls(event, service):
    event_start = isoparse(event['start']['dateTime'])
    event_end = isoparse(event['end']['dateTime'])
    event_summary = event.get('summary', 'No Summary')
    st.sidebar.write(f"**{event_summary}**: {event_start} - {event_end}")
    col1, col2 = st.sidebar.columns([1, 1])
    with col1:
        if st.button(f"Edit", key=f"edit_{event['id']}"):
            st.sidebar.warning("Edit functionality not implemented yet.")
    with col2:
        if st.button(f"Delete", key=f"delete_{event['id']}"):
            try:
                service.events().delete(calendarId='primary', eventId=event['id']).execute()
                st.sidebar.success(f"Event deleted successfully.")
            except googleapiclient.errors.HttpError as error:
                st.sidebar.error(f"An error occurred while deleting event {event['id']}: {error}")

def handle_conflicts(conflicting_event, event_datetime_sri_lanka, event_end, study_duration, existing_events):
    st.session_state.conflicts["initial"] = f"Conflict detected with existing event: {conflicting_event.get('summary', 'No Summary')} from {conflicting_event['start']['dateTime']} to {conflicting_event['end']['dateTime']}"
    st.warning(st.session_state.conflicts["initial"])
    free_times = suggest_free_times(existing_events, study_duration, event_datetime_sri_lanka)
    st.session_state.free_times["initial"] = free_times

def clear_conflict_state():
    st.session_state.conflicts.pop("initial", None)
    st.session_state.free_times.pop("initial", None)

def handle_scheduling_buttons():
    if "initial" in st.session_state.free_times:
        free_times = st.session_state.free_times["initial"]
        st.write("Suggested free times:")
        col1, col2 = st.columns(2)
        with col1:
            if free_times:
                st.button(f"Schedule at {free_times[0]}", key=f"suggest_0")
            if len(free_times) > 1:
                st.button(f"Schedule at {free_times[1]}", key=f"suggest_1")
        with col2:
            if len(free_times) > 2:
                st.button(f"Schedule at {free_times[2]}", key=f"suggest_2")
            if len(free_times) > 3:
                st.button(f"Schedule at {free_times[3]}", key=f"suggest_3")
        if len(free_times) > 4:
            if st.button("View More"):
                for i in range(4, len(free_times)):
                    st.button(f"Schedule at {free_times[i]}", key=f"suggest_{i}")

def handle_event_creation(event_subject, event_description, study_duration, event_datetime_sri_lanka, service):
    if st.button('Schedule Event'):
        if not event_subject or not event_description:
            st.error("Please fill in all the fields to schedule an event.")
        else:
            with st.spinner('Creating events...'):
                color_id = get_color_id(event_subject)
                intervals = [1, 7, 16, 35, 90, 180, 365]
                success = True
                history = []
                new_conflicts = False

                for interval in intervals:
                    event_datetime_interval = event_datetime_sri_lanka + datetime.timedelta(days=interval)
                    event_end_interval = event_datetime_interval + datetime.timedelta(minutes=study_duration)

                    conflicting_event = check_conflicts(event_datetime_interval, event_end_interval, existing_events)
                    if conflicting_event:
                        st.session_state.conflicts[interval] = f"Conflict detected for interval {interval} days with event: {conflicting_event.get('summary', 'No Summary')}"
                        st.warning(st.session_state.conflicts[interval])
                        free_times = suggest_free_times(existing_events, study_duration, event_datetime_interval)
                        st.session_state.free_times[interval] = free_times
                        new_conflicts = True
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
                        created_event = service.events().insert(calendarId='primary', body=new_event).execute()
                        history.append(created_event['id'])
                    except googleapiclient.errors.HttpError as error:
                        st.error(f"An error occurred while creating an event: {error}")
                        success = False

                if success and not new_conflicts:
                    st.success('Events Created Successfully ✔')
                    if st.button("Undo Events"):
                        for event_id in history:
                            try:
                                service.events().delete(calendarId='primary', eventId=event_id).execute()
                            except googleapiclient.errors.HttpError as error:
                                st.error(f"An error occurred while deleting event {event_id}: {error}")
                        st.success("All created events have been undone.")
                elif not success:
                    st.warning('Some events were not created due to conflicts.')

def main():
    if "conflicts" not in st.session_state:
        st.session_state.conflicts = {}
    if "free_times" not in st.session_state:
        st.session_state.free_times = {}

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

    # Date picker for existing events preview
    selected_date = st.sidebar.date_input("Select a date to view existing events:")
    time_min = datetime.datetime.combine(selected_date, datetime.time.min).isoformat() + 'Z'
    time_max = datetime.datetime.combine(selected_date, datetime.time.max).isoformat() + 'Z'
    existing_events = get_existing_events(service, time_min=time_min, time_max=time_max)

    # Display existing events with edit/delete options in modern UI
    st.sidebar.title('Existing Events')
    for event in existing_events:
        display_event_with_controls(event, service)

    event_date = st.date_input("Enter the date you first studied the topic:")
    event_time = st.time_input("Enter the time you first studied the topic:")
    study_duration = st.number_input("Enter the duration of your study session (in minutes):", min_value=1)
    event_subject = st.selectbox("Select the subject of the event:", ["Physics", "Chemistry", "Combined Maths", "Other"])
    event_description = st.text_area("Enter the description of the event:")

    if event_date and event_time:
        event_datetime = datetime.datetime.combine(event_date, event_time)
        event_datetime_sri_lanka = convert_to_sri_lanka_time(event_datetime)
        event_end = event_datetime_sri_lanka + datetime.timedelta(minutes=study_duration)

        conflicting_event = check_conflicts(event_datetime_sri_lanka, event_end, existing_events)
        if conflicting_event:
            handle_conflicts(conflicting_event, event_datetime_sri_lanka, event_end, study_duration, existing_events)
        else:
            clear_conflict_state()
            st.success("No conflicts detected. You can schedule this event.")

    handle_scheduling_buttons()
    handle_event_creation(event_subject, event_description, study_duration, event_datetime_sri_lanka, service)
    st_autorefresh(interval=10 * 1000, key="data_refresh")

if __name__ == '__main__':
    main()
