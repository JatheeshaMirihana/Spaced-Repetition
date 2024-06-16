# Import necessary libraries
from __future__ import print_function
import datetime
import os.path
import pytz
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import streamlit as st
import time

# If modifying these SCOPES, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar.events']

# Function to get color ID based on the subject
def get_color_id(subject):
    subject = subject.lower()
    if subject in ['physics', 'p6','Physics']:
        return '7'  # Peacock
    elif subject in ['chemistry', 'chem']:
        return '6'  # Tangerine
    elif subject in ['combined maths', 'c.m.']:
        return '10'  # Basil
    else:
        return '1'  # Default (Lavender)

# Function to convert time to Sri Lanka time zone
def convert_to_sri_lanka_time(dt):
    sri_lanka_tz = pytz.timezone('Asia/Colombo')
    return dt.astimezone(sri_lanka_tz)

def main():
    """Shows basic usage of the Google Calendar API.
    Creates a Google Calendar API service object and adds spaced repetition events.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('calendar', 'v3', credentials=creds)

    st.title('Google Calendar Event Scheduler')

    # Get event details from the user using Streamlit widgets
    event_date = st.date_input("Enter the date you first studied the topic:")
    event_time = st.time_input("Enter the time you first studied the topic:")
    study_duration = st.number_input("Enter the duration of your study session (in minutes):", min_value=1)
    event_subject = st.selectbox("Select the subject of the event:", ["Physics", "Chemistry", "Combined Maths", "Other"])
    #event_topic = st.text_input("Enter the topic of the event:")
    event_description = st.text_area("Enter the description of the event:")

    if st.button('Schedule Event'):
        if not event_subject or not event_description:
            st.error("Please fill in all the fields to schedule an event.")
        else:
            with st.spinner('Creating events...'):
                # Combine date and time
                event_datetime = datetime.datetime.combine(event_date, event_time)
                event_datetime = pytz.timezone('Asia/Colombo').localize(event_datetime)

                # Convert to Sri Lanka time zone
                event_datetime_sri_lanka = convert_to_sri_lanka_time(event_datetime)

                # Get the subject from the topic and determine the color ID
                color_id = get_color_id(event_subject)

                # Define the spaced repetition intervals in days
                intervals = [1, 7, 16, 35, 90, 180, 365]

                for interval in intervals:
                    event_datetime_interval = event_datetime_sri_lanka + datetime.timedelta(days=interval)
                    
                    event = {
                        'summary': f"{event_subject} - Review",
                        'description': event_description,
                        'start': {
                            'dateTime': event_datetime_interval.isoformat(),
                            'timeZone': 'Asia/Colombo',
                        },
                        'end': {
                            'dateTime': (event_datetime_interval + datetime.timedelta(minutes=study_duration)).isoformat(),
                            'timeZone': 'Asia/Colombo',
                        },
                        'colorId': color_id,
                    }

                    event = service.events().insert(calendarId='primary', body=event).execute()
                    time.sleep(0.2)  # Simulating some delay for each event creation
                st.success('Events Created Successfully ✔')

if __name__ == '__main__':
    main()
