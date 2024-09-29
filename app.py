from __future__ import print_function
import datetime
import os.path
import pytz
import streamlit as st
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow  # Ensure Flow is imported
from googleapiclient.discovery import build
import googleapiclient.errors
import json
from dateutil.parser import isoparse  # <-- Added import here
from streamlit_cookies_manager import CookieManager

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
    cookies = CookieManager()
    creds = None
    
    # Check if token exists in cookies
    if cookies.get("token"):
        creds = Credentials.from_authorized_user_info(json.loads(cookies.get("token")), SCOPES)
    
    # Refresh or initiate a new flow if creds are invalid or expired
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                st.error(f"Error refreshing credentials: {e}")
                creds = None
        else:
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
                    cookies.set("token", creds.to_json(), max_age=3600)  # Save the credentials as a JSON string in cookies
                except Exception as e:
                    st.error(f"Error fetching token: {e}")

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
    # Update session state directly
    st.session_state['event_history'] = updated_history

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
                    # Update session state directly
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

# Sorting function
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
    except googleapiclient.errors.HttpError as error:
        st.error(f"An error occurred: {error}")
        return

    st.title('Google Calendar Event Scheduler')

    # Load or verify event history
    if 'event_history' not in st.session_state:
        history = get_event_history()
        updated_history = verify_events(service, history)
        if history != updated_history:
            save_event_history(updated_history)
        st.session_state['event_history'] = updated_history
    else:
        updated_history = st.session_state['event_history']

    # Right Sidebar for Progress Tracker
    st.sidebar.title('Your Progress')

    # Add sorting dropdown
    sort_option = st.sidebar.selectbox("Sort by:", ["Title", "Date", "Completion"], index=0)

    if 'event_checkboxes' not in st.session_state:
        st.session_state.event_checkboxes = {}

    # Sort events based on selected option
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
                    is_completed = sub_event['completed']
                    event_name = sub_event['name']  # Use description as the name
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
                        st.session_state['event_history'] = updated_history
                        st.sidebar.success(f"Deleted {event['title']} successfully!")
                    except googleapiclient.errors.HttpError as error:
                        st.error(f"An error occurred while deleting event {event_id}: {error}")

    # Display events from selected date
    selected_date = st.sidebar.date_input("Select a date to view events:")
    time_min = datetime.datetime.combine(selected_date, datetime.time.min).isoformat() + 'Z'
    time_max = datetime.datetime.combine(selected_date, datetime.time.max).isoformat() + 'Z'
    existing_events = get_existing_events(service, time_min=time_min, time_max=time_max)

    if not existing_events:
        st.sidebar.write("No events found.")
    else:
        for event in existing_events:
            event_start = isoparse(event['start'].get('dateTime', event['start'].get('date')))
            event_end = isoparse(event['end'].get('dateTime', event['end'].get('date')))
            event_duration = event_end - event_start
            event_summary = event.get('summary', 'No Title')
            event_description = event.get('description', '')
            st.sidebar.write(f"**{event_description}**")  # Display description instead of summary
            st.sidebar.write(f"- Time: {event_start.strftime('%I:%M %p')} - {event_end.strftime('%I:%M %p')}")
            st.sidebar.write(f"- Duration: {event_duration}")
            st.sidebar.write("---")

    if 'event_date' not in st.session_state:
        st.session_state.event_date = datetime.date.today()

    if 'event_time' not in st.session_state:
        st.session_state.event_time = datetime.time(9, 0)

    if 'study_duration' not in st.session_state:
        st.session_state.study_duration = 60  # Default to 60 minutes

    if 'event_subject' not in st.session_state:
        st.session_state.event_subject = "Physics"  # Default to 'Physics'

    if 'event_description' not in st.session_state:
        st.session_state.event_description = ""

    subjects = ["Physics", "Chemistry", "Combined Maths"]  # List of subjects

    st.session_state.event_date = st.date_input("Enter the date you first studied the topic:", value=st.session_state.event_date)
    st.session_state.event_time = st.time_input("Enter the time you first studied the topic:", value=st.session_state.event_time)
    st.session_state.study_duration = st.number_input("Enter the duration of your study session (in minutes):", min_value=1, value=st.session_state.study_duration)

    # Dropdown for subjects
    st.session_state.event_subject = st.selectbox("Select your subject:", subjects, index=subjects.index(st.session_state.event_subject))

    # Text area for event description
    st.session_state.event_description = st.text_area("Enter a description for the study session:", value=st.session_state.event_description)

    intervals = [1, 3, 7, 16, 30, 90, 180]  # Days for review intervals
    interval_actions = {
        1: 'Review notes',
        3: 'Revise key concepts',
        7: 'Revise thoroughly',
        16: 'Solve problems',
        30: 'Revise again',
        90: 'Test yourself',
        180: 'Deep review',
    }

    if st.button("Schedule Event"):
        start_datetime = datetime.datetime.combine(st.session_state.event_date, st.session_state.event_time)
        end_datetime = start_datetime + datetime.timedelta(minutes=st.session_state.study_duration)
        new_event_id = None  # ID for the main event to group sub-events

        new_event = {
            'id': new_event_id,  # Will be updated after creating the first event
            'title': st.session_state.event_description,  # Use description as the main title
            'date': st.session_state.event_date.isoformat(),
            'sub_events': []
        }

        all_events_created = True

        for days in intervals:
            review_date = start_datetime + datetime.timedelta(days=days)
            review_end_datetime = review_date + datetime.timedelta(minutes=st.session_state.study_duration)
            
            event_body = {
                'summary': f"Day {days}: {interval_actions[days]}",
                'description': st.session_state.event_description,
                'start': {
                    'dateTime': review_date.isoformat(),
                    'timeZone': 'Asia/Colombo',
                },
                'end': {
                    'dateTime': review_end_datetime.isoformat(),
                    'timeZone': 'Asia/Colombo',
                },
                'colorId': get_color_id(st.session_state.event_subject),
            }

            try:
                event = service.events().insert(calendarId='primary', body=event_body).execute()
                if new_event_id is None:
                    new_event_id = event['id']
                    new_event['id'] = new_event_id  # Update the main event ID after the first event is created

                new_event['sub_events'].append({
                    'id': event['id'],
                    'name': f"Day {days}: {interval_actions[days]}",  # Set subtitle as "Day X: [Action]"
                    'completed': False
                })

            except googleapiclient.errors.HttpError as error:
                st.error(f"An error occurred: {error}")
                all_events_created = False
                break  # Exit if there's an error in event creation

        if all_events_created:
            st.success("All review events created successfully!")
            updated_history['created_events'].append(new_event)
            save_event_history(updated_history)

            # Update session state directly
            st.session_state['event_history'] = updated_history

            # Reset input fields
            st.session_state.event_date = datetime.date.today()
            st.session_state.event_time = datetime.time(9, 0)
            st.session_state.study_duration = 60
            st.session_state.event_subject = "Physics"
            st.session_state.event_description = ""

if __name__ == '__main__':
    main()