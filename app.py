import datetime
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

def convert_to_sri_lanka_time(dt: datetime.datetime) -> datetime.datetime:
    sri_lanka_tz = pytz.timezone('Asia/Colombo')
    return dt.astimezone(sri_lanka_tz)

def get_credentials():
    creds = None
    
    # Initialize token in session state if not present
    if 'token' not in st.session_state:
        st.session_state['token'] = None

    # Check if token exists and convert it from a JSON string to a dictionary
    if st.session_state['token']:
        creds = Credentials.from_authorized_user_info(json.loads(st.session_state['token']), SCOPES)
    
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
            code = st.experimental_get_query_params().get('code')
            if 'code' in st.experimental_get_query_params():
                try:
                    # Fetch authorization code
                    code = st.experimental_get_query_params()['code'][0]
        
                    # Exchange code for tokens
                    flow.fetch_token(code=code)
                    creds = flow.credentials
        
                    # Save the credentials in session state
                    st.session_state['token'] = creds.to_json()
        
                    # Clear the query parameters to prevent reusing the code
                    st.experimental_set_query_params()  # Clears the 'code' from the URL

                    st.success("Authorization successful! You can now proceed.")

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

def verify_events(service, history):
    updated_history = {'created_events': []}
    for event in history['created_events']:
        sub_events = []
        for sub_event in event['sub_events']:
            if event_exists(service, sub_event['id']):
                sub_events.append(sub_event)
        if sub_events:
            event['sub_events'] = sub_events
            updated_history['created_events'].append(event)
    return updated_history

def event_exists(service, event_id):
    try:
        service.events().get(calendarId='primary', eventId=event_id).execute()
        return True
    except googleapiclient.errors.HttpError:
        return False

def toggle_completion(service, event_id, sub_event_id):
    history = st.session_state['event_history']
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
                            if not calendar_event['summary'].startswith("Completed: "):
                                calendar_event['summary'] = f"Completed: {calendar_event['summary']}"
                            calendar_event['colorId'] = '8'  # Graphite
                        else:
                            if calendar_event['summary'].startswith("Completed: "):
                                calendar_event['summary'] = calendar_event['summary'].replace("Completed: ", "", 1)
                            calendar_event['colorId'] = sub_event['originalColorId']
                        service.events().update(calendarId='primary', eventId=sub_event_id, body=calendar_event).execute()
                    except googleapiclient.errors.HttpError as error:
                        st.error(f"An error occurred while updating event {sub_event_id}: {error}")
                    st.session_state['event_history'] = history
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
        st.stop()

    try:
        service = build('calendar', 'v3', credentials=creds)
    except googleapiclient.errors.HttpError as error:
        st.error(f"An error occurred: {error}")
        st.stop()

    st.title('Google Calendar Event Scheduler')

    if 'event_history' not in st.session_state:
        history = {'created_events': []}
        st.session_state['event_history'] = history
    else:
        history = st.session_state['event_history']

    updated_history = verify_events(service, history)
    st.session_state['event_history'] = updated_history

    st.sidebar.title('Your Progress')
    sort_option = st.sidebar.selectbox("Sort by:", ["Title", "Date", "Completion"], index=0)
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
                    event_name = sub_event['name']
                    if is_completed:
                        event_name = f"~~{event_name}~~"
                    st.checkbox(
                        event_name,
                        value=is_completed,
                        key=f"cb_{sub_event_id}",
                        on_change=toggle_completion,
                        args=(service, event_id, sub_event_id)
                    )
            with col2:
                if st.button("🗑️", key=f"delete_main_{event_id}"):
                    try:
                        for sub_event in event['sub_events']:
                            service.events().delete(calendarId='primary', eventId=sub_event['id']).execute()
                        updated_history['created_events'] = [e for e in updated_history['created_events'] if e['id'] != event_id]
                        st.session_state['event_history'] = updated_history
                        st.sidebar.success(f"Deleted {event['title']} successfully!")
                    except googleapiclient.errors.HttpError as error:
                        st.error(f"An error occurred while deleting event {event_id}: {error}")

    selected_date = st.sidebar.date_input("Select a date to view events:")
    tz = pytz.timezone('Asia/Colombo')
    time_min = tz.localize(datetime.datetime.combine(selected_date, datetime.time.min)).isoformat()
    time_max = tz.localize(datetime.datetime.combine(selected_date, datetime.time.max)).isoformat()

    existing_events = get_existing_events(service, time_min=time_min, time_max=time_max)

    if existing_events:
        st.write(f"Events on {selected_date}:")
        for event in existing_events:
            st.write(f"- {event['summary']}")
    else:
        st.write(f"No events found on {selected_date}.")

if __name__ == "__main__":
    main()
