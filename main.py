import asyncio
import datetime

import discord
from discord.ext import commands
import json
import os
import uuid


from urllib.parse import urlsplit
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import configparser



intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents = intents)


SCOPES = ['https://www.googleapis.com/auth/calendar']
saved_calendar_path = 'saved_calendars.json' # saves channelids and associated calendar ids in a json file.

# if you wanted to set up your own calendar discord bot, you would need to make your own google cloud project and replace these authorization thingies
# tutorial on this: https://stateful.com/blog/events-in-the-google-calendar-API

config = configparser.ConfigParser()
config.read("config.ini")

API_CALLBACK_FOR_PUSH_NOTIFICATIONS = config["DEFAULT"]["api_callback_for_push_notifications"]
SERVICE_ACCOUNT_FILE = config["DEFAULT"]["service_account_file"]
SERVICE_ACCOUNT_EMAIL = config["DEFAULT"]["service_account_email"]
DISCORD_BOT_TOKEN = config["DEFAULT"]["discord_bot_token"]

def get_delegate_credentials():

    credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    delegated_credentials = credentials.with_subject(SERVICE_ACCOUNT_EMAIL)
    return delegated_credentials

# bot only responds to messages that start with !calendar
@bot.command() # !calendar test 1 2 3
async def calendar(ctx, *args):
    print(ctx, args)
    # ctx is a context object, includes channel ID
    # in argument list we get test 1 2 3
    argNum = len(args)
    print(len(args))
    if argNum <= 0:
        await help(ctx)
        return
    task_desc = args[0] # task_desc could be help, register, display, notifyeventcreation
    if task_desc == "help":
        await help(ctx)
        return

    if task_desc =="extendedhelp":
        await extendedhelp(ctx)
        return

    if task_desc == "register":
        await registerCalendar(ctx, args)
        return

    if task_desc == "display" or task_desc == "show":
        await showDays(ctx, args)
        return

    if task_desc == "notifyeventcreation" or task_desc == "push" or task_desc == "watch":
        await notify_event_creation(ctx, args)
        return

    if task_desc == "channelinfo" or task_desc == "info" or task_desc == "channel-info" or task_desc == "channel info":
        await show_channel_information(ctx, args)
        return

    if task_desc == "delete":
        await show_channel_information(ctx, args)
        return

    # delete calendar id
    await help(ctx) # if the task_desc is unknown show help again so user may correct their spelling or something

# compile a message to display the events in the next few days in all calendars registered to the channel that issued the command.
async def showDays(ctx, args):
    days = 7
    calendar_name_filter = None
    if len(args) > 1:
        days_raw = args[1]
        if days_raw.isnumeric():
            days = int(days_raw)
    if len(args) > 2:
        calendar_name_filter = [args[2]]

    today = datetime.datetime.utcnow().date()
    mintime = datetime.datetime(today.year, today.month, today.day) # sets time to 00:00:00
    mintime = mintime.isoformat() + 'Z'

    print(mintime)
    maxtime = datetime.datetime(today.year, today.month, today.day) + datetime.timedelta(days=days + 1) # set to days+1 at 00:00:00.
    maxtime = maxtime.isoformat() + "Z"

    calendar_ids = getSavedCalendarsForChannel(str(ctx.channel.id))

    if len(calendar_ids) == 0:
        await ctx.send("Calendar Bot does not know any Calendars associated with this channel.")
        return

    # authenticate access through an email address invited to have access to the calendars.
    delegated_credentials= get_delegate_credentials()

    discord_events = []
    service = build('calendar', 'v3', credentials=delegated_credentials)
    for calendarId in calendar_ids:  # loop through all registered calendars and pull their events into the discord_events list

        try:
            cal_data = service.events().list(calendarId=calendarId, timeMin=mintime, singleEvents=True, timeMax=maxtime, orderBy='startTime').execute()
            #url = "https://www.googleapis.com/calendar/v3/calendars/" + calendarId + "/events?timeMin="+mintime+"&singleEvents=True&orderBy=startTime&timeMax="+maxtime+"&key=" + google_api_key
            #response = requests.get(url)

            cal_name = cal_data['summary']

            if calendar_name_filter != None:
                if cal_name not in calendar_name_filter:
                    continue # skip calendars that are not in the filter.
            events = cal_data['items']

            for event in events:
                start = (event['start'])
                if 'date' in start:
                    date_s = start['date']  # for events that take the full day
                    date_time = datetime.datetime.strptime(date_s, "%Y-%m-%d")
                    date = date_time.strftime("%d.%m.%Y")
                else:
                    date_s = start['dateTime']
                    date_s = date_s.split("+")[0]
                    date_time = datetime.datetime.strptime(date_s, "%Y-%m-%dT%H:%M:%S")
                    date = date_time.strftime("%d.%m.%Y   %H:%M")
                event_name = event['summary']
                discord_event_string = f"{date_time.strftime('%A')} {str(date)}   **{event_name}**   ({cal_name})\n"
                discord_events.append((date_time, discord_event_string))
        except HttpError:
            await ctx.send(f"Calendar Bot was not granted access to a Calendar. Please make sure to invite the Email address: {SERVICE_ACCOUNT_EMAIL} to have access to your Google Calendar. The Calendar ID: {calendarId}")
            return

    if len(discord_events) > 0:
        discord_events = [x for _, x in sorted(discord_events)]
        out = "".join(discord_events)
        quote_form = '>>> {}'.format(out)
        await ctx.send(quote_form)
    else:
        await ctx.send("No events in calendar")

#show a list of commands with description
async def help(ctx):
    await ctx.send(f"Calendar Bot can display a Google Calendar or notify you of newly created events.\n\n"
                   f"Commands:\n"
                   f"`!calendar register <Google Calendar ID>` Calendar Bot will remember your Google Calendar and can later display it. You can register multiple Calendars in a single Channel.\n"
                   f"`!calendar display` show Events in the registered Calendars for the next 7 days.\n"
                   f"`!calendar display 14` You can adjust the timespan for the displayed Events. Here the timespan is set to 14 days.\n"
                   f"`!calendar display 7 \"<calendar name>\"` Calendar Bot can display a specific calendar indicated by their name.\n"
                   f"`!calendar watch <Google Calendar ID>` Calendar Bot will notify you of newly created Events for the given Calendar.\n"
                   f"`!calendar info` Calendar Bot shows you which calendars are registered or watched in this channel.\n"
                   f"`!calendar help` displays this help message again.\n"
                   f"`!calendar extendedhelp` displays moooooaaaarrrr help text.\n\n"
                   f"You can find a Calendar's ID by vising the webpage of google calendar. Open your Calendar's settings and "
                   f"scroll to the section 'Integrate Calendar' The ID should look like this: <random numbers and letters>@group.calendar.google.com")

async def extendedhelp(ctx):
    await ctx.send(f"There are a few alternative command names:\n"
                   f"`!calendar display` = `!calendar show`\n"
                   f"`!calendar watch` = `push` = `notifyeventcreation`\n"
                   f"`!calendar info` = `channelinfo`= `channel-info` = `\"channel info\"`")

#check if calendar id exists. save calendar with reference to the server and channel
async def registerCalendar(ctx, args):
    if len(args) <= 1:
        await ctx.send(f"To register a Google Calendar: \n"
                       f"1. Invite the the Email address {SERVICE_ACCOUNT_EMAIL} to have access to your Google Calendar. To do this, visit the webpage of google calendar. Open your calendars's settings and scroll to the section 'Für bestimmte Personen oder Gruppen freigeben'\n"
                       f"2. Then find and copy the Calendar ID in the section 'Integrate Calendar', a little further down.\n"
                       f"3. In this discord channel send the command: `!calendar register the_calendar_id_you_just_copied`")
    else:
        calendar_id_raw = args[1]
        calendarID= str(calendar_id_raw)
        # try to reach the calendar ID

        # authenticate access through an email address invited to have access to the calendars.
        delegated_credentials = get_delegate_credentials()
        service = build('calendar', 'v3', credentials=delegated_credentials)
        try:
            cal_data = service.events().list(calendarId=calendarID, maxResults=2).execute()
            cal_name = cal_name = cal_data['summary']
        except HttpError as e:
            await ctx.send(f"Calendar Bot was unable to access this Calendar. "
                           f"Please make sure to invite the Email address: {SERVICE_ACCOUNT_EMAIL} to have "
                           f"access to your Google Calendar. You could also double check the ID. "
                           f"You can find the ID by vising the webpage of google calendar. Open your calendar's settings and scroll to the section 'Integrate Calendar'. "
                           f"The ID should look like this: <random numbers and letters>@group.calendar.google.com\n\n"
                           f"Calendar Bot has encountered the following Error: {e}")
            return
        channel_id = str(ctx.channel.id)
        calendar_ids_for_this_channel = saveCalendarForChannel(ctx, channel_id, calendar_id_raw)
        await ctx.send(f"Calendar Bot now knows that {len(calendar_ids_for_this_channel)} calendar(s) belong to this channel")
    pass

async def notify_event_creation(ctx, args):
    if len(args) <= 1:
        await ctx.send(f"Sign up for event creation notifications for a Google Calendar: \n"
                       f"1. Invite the the Email address {SERVICE_ACCOUNT_EMAIL} to have access to your Google Calendar. To do this, visit the webpage of google calendar. Open your calendars's settings and scroll to the section 'Für bestimmte Personen oder Gruppen freigeben'\n"
                       f"2. Then find and copy the Calendar ID in the section 'Integrate Calendar', a little further down.\n"
                       f"3. In this discord channel send the command: `!calendar notifyeventcreation the_calendar_id_you_just_copied`")
    else:
        calendar_id_raw = args[1]
        calendarID= str(calendar_id_raw)

        save_data = getSavedWatchData(str(ctx.channel.id))
        if calendarID in save_data:
            await ctx.send(f"Calendar Bot is already listening to push notifications for this Calendar-ID.")
            return

        # register bot at calendar api for push notifications on event creation.
        # https://developers.google.com/calendar/api/guides/push
        await _create_new_watch_subscription(ctx, calendarID, ctx.channel.id)

async def _create_new_watch_subscription(discord_channel, calendarID:str, channelid:int):
    if discord_channel == None:
        discord_channel = bot.get_channel(channelid)
        if discord_channel == None:
            print("Discord Channel for a push notification could not be found in discord. Channel might be deleted. Not re-subscribing.")
    cal_uuid = uuid.uuid1()
    token = channelid

    delegated_credentials = get_delegate_credentials()
    service = build('calendar', 'v3', credentials=delegated_credentials)

    body = {'id': str(cal_uuid),
            'type': "web_hook",
            'address': API_CALLBACK_FOR_PUSH_NOTIFICATIONS + "/callback",
            'token': str(token)}
    try:
        data = service.events().watch(calendarId=calendarID, body=body).execute()
        # data = {'kind': 'api#channel', 'id': '2b77ae26-cbe1-11ed-981c-cf2ae50fa78c', 'resourceId': 'nLR4uoL1fandShtZSbrnMTRC7Zk', 'resourceUri': 'https://www.googleapis.com/calendar/v3/calendars/3d3818dd4d2e0bab2152b10e15587669709315ad5f0b3001d0e4acab139896bb%40group.calendar.google.com/events?alt=json', 'token': '1068140692901216326', 'expiration': '1680445147000'}
        # print(data)
        saveWatchData(discord_channel, str(channelid), calendarID, token, str(cal_uuid), data["resourceId"], data["expiration"])
        await discord_channel.send(f"Calendar Bot is now listening for push notifications for this Calendar-ID")
    except HttpError as err:
        await discord_channel.send(
            f"Calendar Bot encountered an error when asking google calendar api to make push notifications for the Calendar-ID. {err}")
        print(err)

async def new_event_creation_callback_display(Goog_Resource_URI, Goog_Channel_Expireation, Goog_Channel_Token, Goog_Channel_Id):
    #print("google notification for", X_Goog_Resource_URI, "expiration data", X_Goog_Channel_Expiration, "for channel",
          #X_Goog_Channel_Token, "; notification channel id:", X_Goog_Channel_ID)

    channel = bot.get_channel(int(Goog_Channel_Token))
    print(Goog_Resource_URI)
    if channel == None:
        print("Could not find the Channel for the push notification. This could happen when the channel is deleted. Should not renew the notification channel at google api")
        return

    # find newly created event in for the calendar.
    # we get a push notification if *anything* changes. So if something is deleted, or changed.
    # I think we only care about new events though.

    split_url = urlsplit(Goog_Resource_URI)
    calendarId:str = str(split_url.path.split("/")[4])
    calendarId = calendarId.replace("%40", "@")

    now = datetime.datetime.utcnow()
    updateMin = now - datetime.timedelta(minutes=2)# set to days+1 at 00:00:00.
    updateMin = updateMin.isoformat() + "Z"
    print(updateMin)

    delegate_credentials = get_delegate_credentials()
    service = build('calendar', 'v3', credentials=delegate_credentials)
    st = ''
    try:
        cal_data = service.events().list(calendarId=calendarId, updatedMin=updateMin).execute()
        cal_name = cal_data['summary']
        events = cal_data['items']
        for event in events:
            if 'status' in event:
                if event['status'] == 'cancelled':
                    #event was cancelled.
                    pass
                else: # a new event will have a status of confirmed or something else.
                    if 'summary' in event:
                        event_name = event['summary']
                        start = (event['start'])
                        if 'date' in start:
                            start_s = start['date']  # for events that take the full day
                            start_time = datetime.datetime.strptime(start_s, "%Y-%m-%d")
                            date = start_time.strftime("%d.%m.%Y")
                        else:
                            start_s = start['dateTime']
                            start_s = start_s.split("+")[0]
                            start_time = datetime.datetime.strptime(start_s, "%Y-%m-%dT%H:%M:%S")
                            end_s = event['end']['dateTime']
                            end_time = datetime.datetime.strptime(end_s.split("+")[0], "%Y-%m-%dT%H:%M:%S")

                            duration = end_time - start_time
                            if duration.days > 0:
                                duration_out = str(duration.days) + " days"
                            elif duration.seconds < 3600:
                                duration_out = str(duration).split(":")[1] + " minutes"
                            else:
                                duration_out = ":".join(str(duration).split(":")[0:2]) + " hours"
                            date = f"{start_time.strftime('%A')}   {start_time.strftime('%d.%m.%Y   %H:%M')}\nDuration: {duration_out}"

                        if 'description' in event:
                            desc = event['description']
                            st = st + f"**{event_name}**\n\n{str(date)}\n\n{desc}\n"
                        else:
                            st = st + f"**{event_name}**\n\n{str(date)}\n"
        if st!= '':
            await channel.send(f"New Event created for Calendar {cal_name}")
            quote_form = '>>> {}'.format(st)
            await channel.send(quote_form)
    except HttpError as e:
        await channel.send(
            f"A registered Calendar has been changed. However, Calendar Bot was not granted access to the Calendar, and cannot tell you anything about the change. Please make sure to invite the Email address: {SERVICE_ACCOUNT_EMAIL} to have access to your Google Calendar. The Calendar ID: {calendarId}. Error Massage: {e}")
        print("Error on reading updated changes for calendar.", e)
    except Exception as anythingElse:
        await channel.send(f"Calendar Bot got an Error. {anythingElse}")

async def show_channel_information(ctx, args):
    if os.path.exists(saved_calendar_path):
        f = open(saved_calendar_path)
        data = json.load(f)
        f.close()
        if str(ctx.channel.id) in data:
            alldata = data[str(ctx.channel.id)]
            await ctx.send(f"Here is the saved Data for this channel:")
            await ctx.send(f">>> {alldata}")
        else:
            await ctx.send(f"There are no calendars registered or watched for this channel. Calendar Bot does not have any saved data to show yet.")
    else:
        await ctx.send(
            f"There are no calendars registered or watched for this server. Calendar Bot does not have any saved data to show yet.")



# count downtime somewhere for scheduled display


# we might be saving a lot of calendars. There is no real need to have them all in cache at once. I do not expect that people will want to display their calendar super often.
# it's probably better to save the data in a legit database. like sqlite or something. though. maybe not. idk.
def getSavedCalendarsForChannel(channel: str):
    if os.path.exists(saved_calendar_path) :
        f = open(saved_calendar_path)
        data = json.load(f)
        f.close()
        if channel in data:
            if "display" in data[channel]:
                return data[channel]["display"]
    return []

def getSavedWatchData(channel: str):
    if os.path.exists(saved_calendar_path):
        f = open(saved_calendar_path)
        data = json.load(f)
        f.close()
        if channel in data:
            if "watch" in data[channel]:
                return data[channel]["watch"]
    return []

def saveWatchData(discord_channel, channel:str, calendarid:str, token:str, id:str, resourceID:str, expiration_unix:str):
    if os.path.exists(saved_calendar_path):
        f = open(saved_calendar_path)
        data = json.load(f)
        f.close()
    else:
        data = {}

    if channel in data: # checks if channel is known. can either have a display or a watch section.
        saved_channel = data[channel]
        if "watch" in saved_channel:
            if calendarid in saved_channel["watch"]:
                #ctx.send("Calendar Bot is already listening to push notifications for this Calendar-ID.")
                # override existing data, for creating a new watch subscription when previous one expires
                data[channel]["watch"][calendarid] = {"caluuid": id, "token": token, "resourceID": resourceID, "expiration": expiration_unix}
                discord_channel.send(f"Calendar Bot has re-subscribed the watch notifications for calendar {calendarid}")
            else:
                # watch existiert, aber nicht diese calendar id
                data[channel]["watch"][calendarid] = {"caluuid": id, "token": token, "resourceID": resourceID, "expiration": expiration_unix}
        else: # channel is known but no watch section yet.
            data[channel]["watch"] = {}
            data[channel]["watch"][calendarid] = {"caluuid": id, "token": token, "resourceID": resourceID, "expiration": expiration_unix}
    else:
        data[channel] = {}
        data[channel]["watch"] = {}
        data[channel]["watch"][calendarid] = {"caluuid": id, "token": token, "resourceID": resourceID, "expiration": expiration_unix} #this is the first calendar id for this channel

    # saving channels and their associated calendar ids in a json file
    print("writing json ", json)
    with open(saved_calendar_path, 'w') as f:
        json.dump(data, f)
    return data[channel]["watch"]

def saveCalendarForChannel(ctx, channel: str, calendarid :str):
    if os.path.exists(saved_calendar_path):
        f = open(saved_calendar_path)
        data = json.load(f)
        f.close()
    else:
        data = {}

    if channel in data: # checks if channel is known. can either have a display or a watch section.
        saved_channel = data[channel]
        if "display" in saved_channel:
            if calendarid in saved_channel["display"]:
                ctx.send("Calendar Bot already knows this Calendar-ID is associated with this channel")
            else:
                calendarids = saved_channel["display"]
                calendarids.append(calendarid)
                data[channel]["display"] = calendarids  # add new calendar id to already saved list of calendar ids for this channel
        else: # channel is known but no display section yet.
            data[channel]["display"] = [calendarid]
    else:
        data[channel] = {}
        data[channel]["display"] = [calendarid] #this is the first calendar id for this channel

    # saving channels and their associated calendar ids in a json file
    print("writing json ", json)
    with open(saved_calendar_path, 'w') as f:
        json.dump(data, f)
    return data[channel]["display"]


import time
def cnt_loop():
    while(True):
        time_unix = time.time()

        if os.path.exists(saved_calendar_path):
            f = open(saved_calendar_path)
            data = json.load(f)
            f.close()
        else:
            data = {}

        for channel in data:
            channeldata = data[channel]
            if 'watch' in channeldata:
                for cal_id in channeldata['watch']:
                    cal_data = channeldata['watch'][cal_id]
                # calendar watched for this channel
                    if 'expiration' in cal_data:
                        expirationdate = cal_data['expiration']
                        expiration_seconds = int(expirationdate) / 1000

                        if (expiration_seconds - time.time() <= 28800): # if expiration time is reached in 8 or less hours
                            # make a new subscription, overriding the data for the old one
                            asyncio.run_coroutine_threadsafe(
                                    _create_new_watch_subscription(None, cal_id, int(channel)),
                                    bot.loop)
                                # google suggests to not delete the old subscription and simply let it expire.
                    else:  # there should be a subscription, but it's missing its expiration data.
                        # also create a new subscription
                        asyncio.run_coroutine_threadsafe(
                            _create_new_watch_subscription(None, cal_id, int(channel)),
                            bot.loop)


        time.sleep(28600)

        # check all watched calendars and renew their notification channels

        # check auto display times


def start_cnt_Thread():
    t = threading.Thread(name = "count", target=cnt_loop)
    t.setDaemon(True)
    t.start()


# http server for calendar watch callback :)
from fastapi import FastAPI
import uvicorn
import threading
from fastapi import Header
from typing import Union
from typing_extensions import Annotated
from fastapi import Request

app = FastAPI()
@app.get("/", status_code=200) # http://localhost:8002/
async def root():
    return {"received"}


#https://developers.google.com/calendar/api/guides/push
@app.post("/callback", status_code=200)
async def callback(X_Goog_Channel_ID: Annotated[Union[str, None], Header()] = None,
                   X_Goog_Channel_Token: Annotated[Union[str, None], Header()] = None,
                   X_Goog_Channel_Expiration: Annotated[Union[str, None], Header()] = None,
                   X_Goog_Resource_ID: Annotated[Union[str, None], Header()] = None,
                   X_Goog_Resource_URI: Annotated[Union[str, None], Header()] = None,
                   X_Goog_Resource_State: Annotated[Union[str, None], Header()] = None,
                   X_Goog_Message_Number: Annotated[Union[str, None], Header()] = None):
    asyncio.run_coroutine_threadsafe(new_event_creation_callback_display(X_Goog_Resource_URI, X_Goog_Channel_Expiration, X_Goog_Channel_Token, X_Goog_Channel_ID), bot.loop)
    print("google notification for", X_Goog_Resource_URI, "expiration data", X_Goog_Channel_Expiration, "for channel",X_Goog_Channel_Token, "; notification channel id:", X_Goog_Channel_ID)
    return {"received"}

def startCallbackServerThread():
    print("starting watch callback thread")
    t = threading.Thread(name="watchCallback", target= start)
    t.setDaemon(True)
    t.start()

def start():
    uvicorn.run(app, host="0.0.0.0", port=8002)


startCallbackServerThread()
start_cnt_Thread()
bot.run(DISCORD_BOT_TOKEN)
