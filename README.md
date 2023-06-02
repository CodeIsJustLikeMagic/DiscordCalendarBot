The Calendar Bot can display a Google Calendar in a Discord channel or notify you of newly created events. 
You can register multiple calendars per channel. Only discord users with the permission to read a channel can see the events.
To this end, I am not using discords server-wide event functionality but rather simple text messages. This allows the use of many different calendars in larger discord communities. 

## How to use a the Discord Bot: ##

Invite the Bot to the Discord Server. Type ```!calendar``` to view the help text.

Show next appointments:
To set this functionality up, use the ```!calendar register <Google Calendar ID>``` command. The Calendar Bot will remember your Google Calendar and can later display it when someone types the command ```!calendar display```. You can register multiple calendars for one discord channel. 

Notify new events:
To set this functionality up, use the ```!calendar watch <Google Calendar ID>``` command. The Calendar Bot will notify you of newly created events for the given calendar.

## Set up your own instance of the Discord Bot: ##

Create a Discord Bot in the discord developer portal.

If you wish to setup your own Discord Bot you need to create a google cloud project to access the google calendar api.
I found this tutorial on this: https://stateful.com/blog/events-in-the-google-calendar-API

The same instructions in text form in case the tutorial is no longer available:
- go to the google cloud platform and create a project
- In the 'IAM and admin' tab, navigate to the sub point 'Service and accounts'
- create a service account with the + option.
- assign a name and press 'create and continue'
- grant the service account the role 'Owner' and press 'continue'
- then press 'done'
- Back on the service accounts page, click the three dots under actions for the newly created service account email. Press manage keys
- On the 'ADD key' dropdown select 'create new key'
- In the subsequent popup select JSON and press 'Create'. Save the Json file and place it next to they main.py python file of the discord bot.
- Input your created service account email as SERVICE_ACCOUNT_EMAIL in main.py
- input the json files name as SERVICE_ACCOUNT_FILE in main.py.
- Next you need to enable the Calender API for your google cloud project.
- navigate to 'APIs and services' -> 'Enable APIs and services'.
- press '+ Enable APIS and Services'
- use the search field to find 'calendar'
- Then enable the Google Calendar API (through klicking on 'Manage')

For the notification, when a new event is created in a calendar, you need to set up a https address that google can reach, for the push notifications.
API_CALLBACK_FOR_PUSH_NOTIFICATIONS
