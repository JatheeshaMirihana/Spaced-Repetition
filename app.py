import datetime
import os
import pickle
import pytz
from dateutil.parser import isoparse
import streamlit as st
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
import googleapiclient.errors

SCOPES = ['https://www.googleapis.com/auth/calendar']

@st.cache(allow_output_mutation=True)
def get_credentials():
    creds = None
    try:
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
    except Exception as e:
        st.error(f"An error occurred during authentication: {e}")
    return creds

def convert_to_sri_lanka_time(dt):
    sri_lanka_tz = pytz.timezone('Asia/Colombo')
    return dt.astimezone(sri_lanka_tz)

def get_existing_events(service, start_date, end_date):
    events_result = service.events().list(
        calendarId='primary', timeMin=start_date.isoformat() + 'Z',
        timeMax=end_date.isoformat() + 'Z', singleEvents=True,
        orderBy='startTime').execute()
    return events_result.get('items', [])

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

def main():
    st.title('Google Calendar Event Scheduler')

    creds = get_credentials()

    if not creds:
        st.error("Unable to authenticate. Please check your credentials and try again.")
        return

    try:
        service = build('calendar', 'v3', credentials=creds)
    except googleapiclient.errors.HttpError as error:
        st.error(f"An error occurred: {error}")
        return

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

        start_date = event_datetime_sri_lanka - datetime.timedelta(days=1)
        end_date = event_datetime_sri_lanka + datetime.timedelta(days=1)
        existing_events = get_existing_events(service, start_date, end_date)

        conflicting_event = check_conflicts(event_datetime_sri_lanka, event_end_datetime, existing_events)
        if conflicting_event:
            st.warning(f"Conflict detected with existing event: {conflicting_event.get('summary', 'No Summary')} from {conflicting_event['start']['dateTime']} to {conflicting_event['end']['dateTime']}")
            free_times = suggest_free_times(existing_events, study_duration, event_datetime_sri_lanka)
            if free_times:
                st.write("Suggested free times:")
                for i, time in enumerate(free_times[:4]):
                    st.button(f"Schedule at {time.strftime('%Y-%m-%d %H:%M')}", key=f"suggest_{i}")
                if len(free_times) > 4:
                    if st.button("View More"):
                        for i, time in enumerate(free_times[4:]):
                            st.button(f"Schedule at {time.strftime('%Y-%m-%d %H:%M')}", key=f"suggest_{i + 4}")
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
                history = []
                new_conflicts = False

                for interval in intervals:
                    event_datetime_interval = event_datetime_sri_lanka + datetime.timedelta(days=interval)
                    event_end_interval = event_datetime_interval + datetime.timedelta(minutes=study_duration)

                    conflicting_event = check_conflicts(event_datetime_interval, event_end_interval, existing_events)
                    if conflicting_event:
                        st.warning(f"Conflict detected for interval {interval} days with event: {conflicting_event.get('summary', 'No Summary')} from {conflicting_event['start']['dateTime']} to {conflicting_event['end']['dateTime']}")
                        free_times = suggest_free_times(existing_events, study_duration, event_datetime_interval)
                        if free_times:
                            st.write(f"Suggested free times for interval {interval} days:")
                            for i, time in enumerate(free_times[:4]):
                                st.button(f"Schedule at {time.strftime('%Y-%m-%d %H:%M')}", key=f"suggest_{i}")
                            if len(free_times) > 4:
                                if st.button("View More"):
                                    for i, time in enumerate(free_times[4:]):
                                        st.button(f"Schedule at {time.strftime('%Y-%m-%d %H:%M')}", key=f"suggest_{i + 4}")
                        new_conflicts = True
                    else:
                        event_body = {
                            'summary': event_subject,
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
                            created_event = service.events().insert(calendarId='primary', body=event_body).execute()
                            history.append(f"Event created for interval {interval} days: {created_event.get('htmlLink')}")
                        except googleapiclient.errors.HttpError as error:
                            st.error(f"An error occurred while creating the event for interval {interval} days: {error}")
                            success = False
                            break

                if success and not new_conflicts:
                    st.success('All events created successfully!')
                    for h in history:
                        st.write(h)
                elif new_conflicts:
                    st.warning("Some events could not be created due to conflicts. Please review and resolve them.")
                else:
                    st.error("An error occurred while creating events. Please try again.")

if __name__ == '__main__':
    main()
