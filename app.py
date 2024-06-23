import datetime
import pytz
import streamlit as st
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os
import pickle

SCOPES = ['https://www.googleapis.com/auth/calendar']

def authenticate_google_account():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    service = build('calendar', 'v3', credentials=creds)
    return service

def get_existing_events(service, start_date, end_date):
    events_result = service.events().list(
        calendarId='primary', timeMin=start_date.isoformat() + 'Z',
        timeMax=end_date.isoformat() + 'Z', singleEvents=True,
        orderBy='startTime').execute()
    return events_result.get('items', [])

def check_conflicts(event_start, event_end, existing_events):
    for event in existing_events:
        start = event['start'].get('dateTime')
        end = event['end'].get('dateTime')
        if not start or not end:
            continue
        start = datetime.datetime.fromisoformat(start[:-1])
        end = datetime.datetime.fromisoformat(end[:-1])
        if (event_start < end and event_end > start):
            return event
    return None

def suggest_free_times(existing_events, duration_minutes, desired_start):
    suggested_times = []
    current_time = desired_start
    end_time = desired_start + datetime.timedelta(days=7)
    duration = datetime.timedelta(minutes=duration_minutes)

    while current_time < end_time:
        conflict = check_conflicts(current_time, current_time + duration, existing_events)
        if not conflict:
            suggested_times.append(current_time)
        current_time += datetime.timedelta(minutes=30)
    return suggested_times

def get_color_id(subject):
    color_mapping = {
        'Chemistry': '1',
        'Physics': '2',
    }
    return color_mapping.get(subject, '10')

def main():
    st.title('Study Event Scheduler')

    event_subject = st.text_input('Event Subject')
    event_description = st.text_input('Event Description')
    event_date = st.date_input('Event Date')
    event_time = st.time_input('Event Time')
    study_duration = st.number_input('Study Duration (minutes)', min_value=1, max_value=1440, value=60)

    if st.button('Check Availability'):
        if not event_subject or not event_description:
            st.error("Please fill in all the fields.")
            return

        event_datetime = datetime.datetime.combine(event_date, event_time)
        event_datetime_sri_lanka = pytz.timezone('Asia/Colombo').localize(event_datetime)
        event_end_datetime = event_datetime_sri_lanka + datetime.timedelta(minutes=study_duration)

        service = authenticate_google_account()

        start_date = event_datetime_sri_lanka - datetime.timedelta(days=1)
        end_date = event_datetime_sri_lanka + datetime.timedelta(days=1)
        existing_events = get_existing_events(service, start_date, end_date)

        conflicting_event = check_conflicts(event_datetime_sri_lanka, event_end_datetime, existing_events)
        if conflicting_event:
            st.session_state.conflicts["initial"] = f"Conflict detected with existing event: {conflicting_event.get('summary', 'No Summary')} from {conflicting_event['start']['dateTime']} to {conflicting_event['end']['dateTime']}"
            st.warning(st.session_state.conflicts["initial"])
            free_times = suggest_free_times(existing_events, study_duration, event_datetime_sri_lanka)
            st.session_state.free_times["initial"] = free_times
        else:
            st.session_state.conflicts.pop("initial", None)
            st.session_state.free_times.pop("initial", None)
            st.success("No conflicts detected. You can schedule this event.")

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

    st_autorefresh(interval=10 * 1000, key="data_refresh")

if __name__ == '__main__':
    main()
