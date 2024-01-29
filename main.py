import asyncio
import datetime
import time
import discord
from discord.ext import commands
import json
import os
import uuid
import numpy as np

from urllib.parse import urlsplit
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import matplotlib.pyplot as plt  # when showing the calendar events as image, image created as table with matplotlib

import configparser

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

SCOPES = ['https://www.googleapis.com/auth/calendar']
saved_calendar_path = 'saved_calendars.json'  # saves channelids and associated calendar ids in a json file.

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
@bot.command()  # !calendar test 1 2 3
async def calendar(ctx, *args):
    print(ctx, args)
    # ctx is a context object, includes channel ID
    # in argument list we get test 1 2 3
    argNum = len(args)
    print(len(args))
    if argNum <= 0:
        await help(ctx)
        return
    task_desc = args[0]  # task_desc could be help, register, display, notifyeventcreation
    if task_desc == "help":
        await help(ctx)
        return

    if task_desc == "extendedhelp":
        await extendedhelp(ctx)
        return

    if task_desc == "register":
        await registerCalendar(ctx, args)
        return

    if task_desc == "setcolor" or task_desc == "color" or task_desc == "setColor" or task_desc == "calendarcolor":
        await setCalendarColor(ctx, args)
        return

    if task_desc == "autodisplay" or task_desc == "autoshow" or task_desc == "autotable":
        await setAutoDisplay(ctx, args)
        return

    if task_desc == "display" or task_desc == "show" or task_desc == "table" or task_desc == "showtable":
        await showDays(ctx, args, True)
        return

    if task_desc == "message" or task_desc == "text" or task_desc == "showtext":
        await showDays(ctx, args, False)
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
    await help(ctx)  # if the task_desc is unknown show help again so user may correct their spelling or something


# retrieves events in the next few days from all calendars registered to the channel that issued the command.
# either compiles result into text or image response
async def showDays(ctx, args, asImage=False, channelid=-1):  # args: show day_count clanedar_name_filter
    if ctx == None:  # for sceduled auto table show, provides channelid instead of ctx object
        ctx = bot.get_channel(channelid)  # this is the same as ctx.channel. So one level down,
        # send works the same but accessing the id is different.
        if ctx == None:
            print("Discord Channel for a auto table show could not be found in discord. "
                  "Channel might be deleted.")
            return
    if channelid == -1:
        channel = str(ctx.channel.id)
    else:
        channel = str(channelid)
    days = 7
    calendar_name_filter = None
    if len(args) > 1:
        days_raw = args[1]
        if days_raw.isnumeric():
            days = int(days_raw)
    if len(args) > 2:
        calendar_name_filter = [args[2]]

    today = datetime.datetime.utcnow().date()

    if asImage:  # set startday to the last monday for table view
        last_monday = today - datetime.timedelta(days=today.weekday())
        days = days + today.weekday()  # shift maxtime forward
        today = last_monday
        angebrochene_woche = days % 7
        if angebrochene_woche > 0:  # set day count to a multiple of 7. always fills whole week
            days = days + (7 - angebrochene_woche)
    mintime = datetime.datetime(today.year, today.month, today.day)  # sets time to 00:00:00
    mintime = mintime.isoformat() + 'Z'

    print(mintime)
    maxtime = datetime.datetime(today.year, today.month, today.day) + datetime.timedelta(
        days=days)  # set to days+1 at 00:00:00.
    maxtime = maxtime.isoformat() + "Z"

    calendar_ids = getSavedCalendarsForChannel(channel)

    if len(calendar_ids) == 0:
        await ctx.send("Calendar Bot does not know any Calendars associated with this channel.\n"
                       "Use `!calendar register` to learn how to register a calendar.")
        return

    # authenticate access through an email address invited to have access to the calendars.
    delegated_credentials = get_delegate_credentials()

    discord_events = []

    service = build('calendar', 'v3', credentials=delegated_credentials)
    for calendarId in calendar_ids:  # loop through all registered calendars and pull their events into the discord_events list

        try:
            cal_data = service.events().list(calendarId=calendarId, timeMin=mintime, singleEvents=True, timeMax=maxtime,
                                             orderBy='startTime').execute()
            # cal_color = service.colors().get().execute() # returns color id-rgb mappings for calendar and events but I don't know which ids belong to which event. they wont tell me their color Id
            # cal_color = service.calendarList().get(calendarId=calendarId).execute() # I think we dont have enough authentication to get colors :/
            # url = "https://www.googleapis.com/calendar/v3/calendars/" + calendarId + "/events?timeMin="+mintime+"&singleEvents=True&orderBy=startTime&timeMax="+maxtime+"&key=" + google_api_key
            # response = requests.get(url)

            cal_name = cal_data['summary']
            cal_color = calendar_ids[calendarId]['color']  # sadly cannot retreive colors from api. Let users set color for discord bot

            if calendar_name_filter is not None:
                if cal_name not in calendar_name_filter:
                    continue  # skip calendars that are not in the filter.
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
                discord_event_info = (date_time.strftime('%A'), str(date), event_name, cal_name, cal_color)
                discord_events.append((date_time, discord_event_info))
        except HttpError:
            await ctx.send(
                f"Calendar Bot was not granted access to the Calendar with ID {calendarId}. Please make sure to invite the Email address: {SERVICE_ACCOUNT_EMAIL} to have access to your Google Calendar. Display instructions with `!calendar register`")
            print()
            return

    if len(discord_events) > 0:
        if asImage:
            await showAsImage(ctx, discord_events)
        else:
            await showAsText(ctx, discord_events)
    else:
        await ctx.send(f"¯\_(ツ)_/¯ No events in calendar in the next {days} days.")

    if channelid != -1:  # when called by autodisplay
        await ctx.send(f"Calendar display triggered by autodisplay function. Type `!calendar help` to learn more.")


# compile events into a text response
async def showAsText(ctx, discord_events):
    discord_events = [x for _, x in sorted(discord_events)]
    event_strings = [f"{weekday} {date}   **{event_name}**   ({cal_name})\n" for
                     weekday, date, event_name, cal_name, cal_color in discord_events]
    out = "".join(event_strings)
    quote_form = '>>> {}'.format(out)
    await ctx.send(quote_form)


# compile events into an image response
async def showAsImage(ctx, event):  # pretty table
    # using matplotlib to draw events as table graphic
    plt.rcParams["figure.autolayout"] = True
    # plt.rcParams.update({'text.color': "black"})
    fig, ax = plt.subplots()
    # style info
    bgc = "#2b2d31"  # background color
    dc = "#383a40"  # date row color
    today_c = "#595c66" # date row color for today
    color_edges = "#4e5058"  # color of the table edges
    color_font = "#ffffff"  # color of font in image
    weekday_strings = ['Monday', 'Tuesday', 'Wednesday', "Thursday", "Friday", "Saturday", "Sunday"]

    # process event info for table
    event = [(dtime, x) for dtime, x in sorted(event)]  # sort events by datetime
    # event_strings = [f"{weekday} {date}   **{event_name}**   ({cal_name})\n" for
    #                 weekday, date, event_name, cal_name in discord_events]

    # need to find out how many full weeks the events cover.
    first_week_num = int(event[0][0].strftime("%W"))
    start_year = int(event[0][0].strftime("%Y"))
    last_week_num = int(event[-1][0].strftime("%W"))
    total_weeks = last_week_num - first_week_num + 1

    table_data = np.array([weekday_strings])
    table_colors = np.array([[bgc, bgc, bgc, bgc, bgc, bgc, bgc]])
    # start_day_table = datetime.datetime.now() - datetime.timedelta(days = int(event[0][0].strftime("%A"))

    startdate = time.asctime(time.strptime('2024 %d 1' % first_week_num, '%Y %W %w'))
    startdate = datetime.datetime.strptime(startdate, '%a %b %d %H:%M:%S %Y')

    # find maximum number of events on a single day in the observed time. -> needed to draw pretty table
    events_by_date = [[(d, x) for d, x in event if d.date() == day_dt.date()] for day_dt in
                      [startdate + datetime.timedelta(days=i) for i in range(total_weeks*7 + 1)]]
    max_events_in_week = max([len(eventlist) for eventlist in events_by_date])

    for week in range(0, total_weeks):
        week_data = []
        week_colors = []
        datesOfWeek_dt = [startdate + datetime.timedelta(days=7 * week + i) for i in range(7)]
        # bug: you can have more than calcount events on one day by having more than one event per calendar on a given day
        # solution: get a list of relevant_events per day first, get max found amount of events per day as calcount.
        # will dynamically expand/shrink size of table to fit all events
        events_by_weekday = [[(d, x) for d, x in event if d.date() == day_dt.date()] for day_dt in datesOfWeek_dt]
        for relevant_events, day_dt in zip(events_by_weekday, datesOfWeek_dt):
            event_strings = np.array([f"{d.strftime('%H:%M')} {x[2]}" for d, x in relevant_events])
            filler = np.array(["" for _ in range(max_events_in_week - len(relevant_events))])
            day_data = np.concatenate((np.array([day_dt.strftime("%d.%m.%Y")]), event_strings, filler))

            event_colors = np.array([x[4] for d, x in relevant_events])
            filler_colors = np.array([bgc for _ in range(max_events_in_week - len(relevant_events))])
            date_color = dc
            if day_dt.date() == datetime.date.today():
                date_color = today_c
            day_color = np.concatenate(([date_color], event_colors, filler_colors))
            # day_color = [dc, bgc, bgc]
            # for day in week
            # [date, events at that date, filled up with "" to get to calcount]
            # add to week_data
            week_data.append(day_data)
            week_colors.append(day_color)

        # reshape week_data
        np_week = np.array(week_data)
        np_week = np.transpose(np_week)
        np_color = np.array(week_colors)
        np_color = np.transpose(np_color)

        # append to table_data
        table_data = np.concatenate((table_data, np_week))
        table_colors = np.concatenate((table_colors, np_color))

    cal1 = "#3f51b5"
    cal2 = "#a79b8e"

    """
    tab = [weekday_strings,
           [22, 23, 24, 25, 26, 27, 28],
           ["18:00 Nelly weg", "", "", "", "19:30 OCT", "", ""],
           ["20:30 Ocean Trident", "", "", "", "", "", ""],
           [29, 30, 31, 1, 2, 3, 4],
           ["18:00 Nelly weg", "", "", "", "19:30 OCT", "", "15:00 PL vs Blue"],
           ["20:30 Ocean Trident", "", "", "", "", "", ""]]

    colors = [[bgc, bgc, bgc, bgc, bgc, bgc, bgc],
              [dc, dc, dc, dc, dc, dc, dc],
              [cal2, bgc, bgc, bgc, bgc, bgc, bgc],
              [cal1, bgc, bgc, bgc, bgc, bgc, bgc],
              [dc, dc, dc, dc, dc, dc, dc],
              [cal2, bgc, bgc, bgc, bgc, bgc, bgc],
              [cal1, bgc, bgc, bgc, bgc, bgc, bgc]]
    """

    # create table
    ytable = ax.table(cellText=table_data, colLabels=None,
                      colWidths=[.4] * 7, loc='center', cellColours=table_colors)

    cellDict = ytable.get_celld()
    for i in range(0, len(weekday_strings)):
        cellDict[(0, i)].set_height(.13)  # weekday row
        cellDict[(0, i)].set_edgecolor(bgc)
        cellDict[(0, i)].set_fill = True
        cellDict[(0, i)].set_text_props(color=color_font, ha="center")

        for j in range(1, len(table_data)):  # event rows + date rows
            cellDict[(j, i)].set_height(0.15)
            cellDict[(j, i)].set_edgecolor(color_edges)
            cellDict[(j, i)].set_text_props(color=color_font, ha="left")
            cellDict[(j, i)].PAD = 0.03
        for j in range(1, len(table_data), max_events_in_week + 1):  # date rows
            cellDict[(j, i)].set_height(.1)

    ytable.set_fontsize(14)
    ax.axis('off')

    fig.canvas.draw()
    bbox = ytable.get_window_extent(fig.canvas.get_renderer())
    #bbox = bbox.from_extents(bbox.xmin - 0, bbox.ymin - 0, bbox.xmax + 2, bbox.ymax + 1)
    bbox_inches = bbox.transformed(fig.dpi_scale_trans.inverted())

    fig.savefig('calendar.png', bbox_inches=bbox_inches)

    # await ctx.send("this is where I would put the calendar image")
    await ctx.send(file=discord.File('calendar.png'))


# show a list of commands with description
async def help(ctx):
    await ctx.send(f"Calendar Bot can display a Google Calendar or notify you of newly created events.\n\n"
                   f"Display Commands:\n"
                   f"`!calendar display` show Events in the registered Calendars for the next 7 days.\n"
                   f"`!calendar display 14` You can adjust the timespan for the displayed Events. Here the timespan is set to 14 days.\n"
                   f"`!calendar display 7 \"<calendar name>\"` Calendar Bot can display a specific calendar indicated by their name.\n"
                   f"`!calendar showtext` shows Events as a text message.\n"
                   f"`!calendar showtext 14` adjust timespan for Events in the text message.\n"
                   f" \nSet up and Register Calendars\n"
                   f"`!calendar register <Google Calendar ID>` Calendar Bot will remember your Google Calendar and can later display it. You can register multiple Calendars in a single Channel.\n"
                   f"For detailed help with the register command :`!calendar register`.\n"
                   f"`!calendar setcolor <Google Calendar ID> <HEX color code>` customize a calendar's color for display.\n"
                   f"`!calendar autodisplay` Calendar Bot will automatically display registered calendars every monday.\n"
                   f"`!calendar autodisplay <1-7 to indicate weekday>` adjust the weekday for autodisplay.\n"
                   f"`!calendar autodisplay 0` disable autodisplay.\n"
                   f"`!calendar watch <Google Calendar ID>` Calendar Bot will notify you of newly created Events for the given Calendar.\n"
                   f"`!calendar info` Calendar Bot shows you which calendars are registered or watched in this channel.\n"
                   f"`!calendar help` displays this help message again.\n"
                   f"`!calendar extendedhelp` displays moooooaaaarrrr help text.\n\n"
                   f"You can find a Calendar's ID by vising the webpage of google calendar. Open your Calendar's settings and "
                   f"scroll to the section 'Integrate Calendar' The ID should look like this: <random numbers and letters>@group.calendar.google.com")


async def extendedhelp(ctx):
    await ctx.send(f"To register a Google Calendar for the `!calendar display` command: \n"
                   f"1. Visit https://calendar.google.com/calendar\n"
                   f"2. On the left, find the calendar you wish to share under 'My calendars'.\n"
                   f"3. Open the calendar's 'Settings and Sharing'\n"
                   f"4. Scroll to the section 'Share with specific people' and click 'Add people'\n"
                   f"5. Add this Email address: {SERVICE_ACCOUNT_EMAIL}\n"
                   f"6. Next, scroll down to the section 'Integrate Calendar' and copy the Calendar ID\n"
                   f"7. In this discord channel send the command: \n`!calendar register paste_the_calendar_id_you_just_copied`\n\n"

                   f"Sign up for event creation notifications for a Google Calendar: \n"
                   f"1. Visit https://calendar.google.com/calendar\n"
                   f"2. On the left, find the calendar you wish to share under 'My calendars'.\n"
                   f"3. Open the calendar's 'Settings and Sharing'\n"
                   f"4. Scroll to the section 'Share with specific people' and click 'Add people'\n"
                   f"5. Add this Email address: {SERVICE_ACCOUNT_EMAIL}\n"
                   f"6. Next, scroll down to the section 'Integrate Calendar' and copy the Calendar ID\n"
                   f"7. In this discord channel send the command: \n`!calendar notifyeventcreation paste_the_calendar_id_you_just_copied`\n\n"


                   f"There are a few alternative command names:\n"
                   f"`!calendar display` = `!calendar showtable` = `!calendar table` = `!calendar show`\n"
                   f"`!calendar showtext` = `!calendar text` = `!calendar message`\n"
                   f"`!calendar setcolor` = `!calendar color` = `!calendar setColor` = `!calendar calendarcolor`\n"
                   f"`!calendar autodisplay` = `!calendar autoshow` = `!calendar autotable`\n"
                   f"`!calendar watch` = `push` = `notifyeventcreation`\n"
                   f"`!calendar info` = `channelinfo`= `channel-info` = `\"channel info\"`")


# check if calendar id exists. save calendar with reference to the server and channel
async def registerCalendar(ctx, args):  # register calendarId (opitonal: colorHEX)
    if len(args) <= 1:
        await ctx.send(f"To register a Google Calendar: \n"
                       f"1. Visit https://calendar.google.com/calendar\n"
                       f"2. On the left, find the calendar you wish to share under 'My calendars'.\n"
                       f"3. Open the calendar's 'Settings and Sharing'\n"
                       f"4. Scroll to the section 'Share with specific people' and click 'Add people'\n"
                       f"5. Add this Email address: {SERVICE_ACCOUNT_EMAIL}\n"
                       f"6. Next, scroll down to the section 'Integrate Calendar' and copy the Calendar ID\n"
                       f"7. In this discord channel send the command: \n`!calendar register paste_the_calendar_id_you_just_copied`")
    else:
        calendar_id_raw = args[1]
        calendarID = str(calendar_id_raw)

        # process optional color argument
        set_Custom_color = False
        custom_color = ""
        if len(args) >= 3:
            color_raw = args[2]
            if is_valid_hexa_code(color_raw):
                set_Custom_color = True
                custom_color = color_raw

        # try to reach the calendar ID
        # authenticate access through an email address invited to have access to the calendars.
        delegated_credentials = get_delegate_credentials()
        service = build('calendar', 'v3', credentials=delegated_credentials)
        try:
            cal_data = service.events().list(calendarId=calendarID, maxResults=2).execute()
            cal_name = cal_data['summary']
        except HttpError as e:
            await ctx.send(f"Calendar Bot was unable to access this Calendar. "
                           f"Please make sure to invite the Email address: {SERVICE_ACCOUNT_EMAIL} to have "
                           f"access to your Google Calendar. You could also double check the ID. "
                           f"You can find the ID by vising https://calendar.google.com/calendar. Open your calendar's settings and scroll to the section 'Integrate Calendar'. "
                           f"The ID should look like this: <random numbers and letters>@group.calendar.google.com\n\n"
                           f"Calendar Bot has encountered the following Error: {e}")
            return
        channel_id = str(ctx.channel.id)
        if set_Custom_color:
            calendar_ids_for_this_channel = saveCalendarForChannel(ctx, channel_id, calendar_id_raw, cal_name,
                                                                   custom_color, True)
        else:
            calendar_ids_for_this_channel = saveCalendarForChannel(ctx, channel_id, calendar_id_raw, cal_name)
        await ctx.send(
            f"Successfully registered Calendar. Calendar Bot now knows that {len(calendar_ids_for_this_channel)} calendar(s) belong to this channel")
    pass


import re


def is_valid_hexa_code(string):
    hexa_code = re.compile(r'^#([a-fA-F0-9]{6}|[a-fA-F0-9]{3})$')
    return bool(re.match(hexa_code, string))


async def setCalendarColor(ctx, args):  # args: setcolor id HEX
    known_calendar_ids = getSavedCalendarsForChannel(str(ctx.channel.id))
    if (len(known_calendar_ids) == 0):
        await ctx.send("Calendar Bot does not know any Calendars associated with this channel."
                       " Use `!calendar register` to register a calendar.")
        return

    if len(args) < 3:  # no calender specified
        await ctx.send(f"Please specify a calendarId and a color\n"
                       f"Known Calendar Ids: `{known_calendar_ids}`\n"
                       f"`!calendar setcolor calendar_id HEX_color_code`")
    else:
        calendar_id_raw = args[1]
        calendarID = str(calendar_id_raw)
        color_raw = args[2]
        if not is_valid_hexa_code(color_raw):
            await ctx.send("The color you provided is not in HEX format. It should look similar to this: #292f72")
        else:
            if calendarID not in known_calendar_ids:
                await ctx.send(
                    f"Calendar Bot does not know this calendar Id yet. {len(known_calendar_ids)} calendar(s) belong to this channel. Check `!calendar info` for registered Calendars.\n"
                    f"Register and apply your color with `!calendar register {calendarID} {color_raw}`")
            else:
                saveCalendarForChannel(ctx, str(ctx.channel.id), calendar_id_raw, color=color_raw, setCustomColor=True)
                await ctx.send("Successfully changed the calendar color.")


async def setAutoDisplay(ctx, args):  # args autodisplay 1
    known_calendar_ids = getSavedCalendarsForChannel(str(ctx.channel.id))
    if (len(known_calendar_ids) == 0):
        await ctx.send("Calendar Bot does not know any Calendars associated with this channel."
                       " Use `!calendar register` to register a calendar.")
        return

    if len(args) >= 2:
        weekday = args[1]
    else:
        weekday = "1"  # default is Monday :)
    if not weekday.isdigit():
        await ctx.send("Please specify the weekday as a numer between 1 and 7.\n"
                       "1 = Monday, 2 = Tuesday, etc\n"
                       "For example: `!calendar autodisplay 1` will display a table view every monday.")
    else:
        weekday = int(weekday)
        saveAutoDisplayWeekday(ctx, str(ctx.channel.id), weekday)
        weekday_strings = ['monday', 'tuesday', 'wednesday', "thursday", "friday", "saturday", "sunday"]
        if weekday >= 1 and weekday <= 7:
            await ctx.send(
                f"Every {weekday_strings[weekday - 1]} Calendar Bot will automatically display your next week.")
        else:
            await ctx.send(
                f"{weekday} is not a number between 1 and 7. Calendar Bot will *not* automatically display your next week.")


async def notify_event_creation(ctx, args):
    if len(args) <= 1:
        await ctx.send(f"Sign up for event creation notifications for a Google Calendar: \n"
                       f"1. Visit https://calendar.google.com/calendar\n"
                       f"2. On the left, find the calendar you wish to share under 'My calendars'.\n"
                       f"3. Open the calendar's 'Settings and Sharing'\n"
                       f"4. Scroll to the section 'Share with specific people' and click 'Add people'\n"
                       f"5. Add this Email address: {SERVICE_ACCOUNT_EMAIL}\n"
                       f"6. Next, scroll down to the section 'Integrate Calendar' and copy the Calendar ID\n"
                       f"7. In this discord channel send the command: \n`!calendar notifyeventcreation paste_the_calendar_id_you_just_copied`")
    else:
        calendar_id_raw = args[1]
        calendarID = str(calendar_id_raw)

        save_data = getSavedWatchData(str(ctx.channel.id))
        if calendarID in save_data:
            await ctx.send(f"Calendar Bot is already listening to push notifications for this Calendar-ID.")
            return

        # register bot at calendar api for push notifications on event creation.
        # https://developers.google.com/calendar/api/guides/push
        await _create_new_watch_subscription(ctx, calendarID, ctx.channel.id)


async def _create_new_watch_subscription(discord_channel, calendarID: str, channelid: int):
    if discord_channel == None:
        discord_channel = bot.get_channel(channelid)
        if discord_channel == None:
            print(
                "Discord Channel for a push notification could not be found in discord. Channel might be deleted. Not re-subscribing.")
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
        saveWatchData(discord_channel, str(channelid), calendarID, token, str(cal_uuid), data["resourceId"],
                      data["expiration"])
        await discord_channel.send(f"Calendar Bot is now listening for push notifications for this Calendar-ID")
    except HttpError as err:
        await discord_channel.send(
            f"Calendar Bot encountered an error when asking google calendar api to make push notifications for the Calendar-ID. {err}")
        print(err)


async def new_event_creation_callback_display(Goog_Resource_URI, Goog_Channel_Expireation, Goog_Channel_Token,
                                              Goog_Channel_Id):
    # print("google notification for", X_Goog_Resource_URI, "expiration data", X_Goog_Channel_Expiration, "for channel",
    # X_Goog_Channel_Token, "; notification channel id:", X_Goog_Channel_ID)

    channel = bot.get_channel(int(Goog_Channel_Token))
    print(Goog_Resource_URI)
    if channel == None:
        print(
            "Could not find the Channel for the push notification. This could happen when the channel is deleted. Should not renew the notification channel at google api")
        return

    # find newly created event in for the calendar.
    # we get a push notification if *anything* changes. So if something is deleted, or changed.
    # I think we only care about new events though.

    split_url = urlsplit(Goog_Resource_URI)
    calendarId: str = str(split_url.path.split("/")[4])
    calendarId = calendarId.replace("%40", "@")

    now = datetime.datetime.utcnow()
    updateMin = now - datetime.timedelta(minutes=2)  # set to days+1 at 00:00:00.
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
                    # event was cancelled.
                    pass
                else:  # a new event will have a status of confirmed or something else.
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
        if st != '':
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
            await ctx.send(
                f"There are no calendars registered or watched for this channel. Calendar Bot does not have any saved data to show yet.")
    else:
        await ctx.send(
            f"There are no calendars registered or watched for this server. Calendar Bot does not have any saved data to show yet.")


# count downtime somewhere for scheduled display


# we might be saving a lot of calendars. There is no real need to have them all in cache at once. I do not expect that people will want to display their calendar super often.
# it's probably better to save the data in a legit database. like sqlite or something. though. maybe not. idk.
def getSavedCalendarsForChannel(channel: str):
    if os.path.exists(saved_calendar_path):
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


def saveWatchData(discord_channel, channel: str, calendarid: str, token: str, id: str, resourceID: str,
                  expiration_unix: str):
    if os.path.exists(saved_calendar_path):
        f = open(saved_calendar_path)
        data = json.load(f)
        f.close()
    else:
        data = {}

    if channel in data:  # checks if channel is known. can either have a display or a watch section.
        saved_channel = data[channel]
        if "watch" in saved_channel:
            if calendarid in saved_channel["watch"]:
                # ctx.send("Calendar Bot is already listening to push notifications for this Calendar-ID.")
                # override existing data, for creating a new watch subscription when previous one expires
                data[channel]["watch"][calendarid] = {"caluuid": id, "token": token, "resourceID": resourceID,
                                                      "expiration": expiration_unix}
                discord_channel.send(
                    f"Calendar Bot has re-subscribed the watch notifications for calendar {calendarid}")
            else:
                # watch existiert, aber nicht diese calendar id
                data[channel]["watch"][calendarid] = {"caluuid": id, "token": token, "resourceID": resourceID,
                                                      "expiration": expiration_unix}
        else:  # channel is known but no watch section yet.
            data[channel]["watch"] = {}
            data[channel]["watch"][calendarid] = {"caluuid": id, "token": token, "resourceID": resourceID,
                                                  "expiration": expiration_unix}
    else:
        data[channel] = {}
        data[channel]["watch"] = {}
        data[channel]["watch"][calendarid] = {"caluuid": id, "token": token, "resourceID": resourceID,
                                              "expiration": expiration_unix}  # this is the first calendar id for this channel

    # saving channels and their associated calendar ids in a json file
    print("writing json ", json)
    with open(saved_calendar_path, 'w') as f:
        json.dump(data, f)
    return data[channel]["watch"]


def saveCalendarForChannel(ctx, channel: str, calendarid: str, cal_name: str = "unnamed",
                           color="#292f72", setCustomColor=False):
    if os.path.exists(saved_calendar_path):
        f = open(saved_calendar_path)
        data = json.load(f)
        f.close()
    else:
        data = {}

    if channel in data:  # checks if channel is known. can either have a display or a watch section.
        saved_channel = data[channel]
        if "display" in saved_channel:
            if calendarid in saved_channel["display"]:
                if setCustomColor:
                    saved_channel["display"][calendarid]["color"] = color
                    ctx.send("Successfully updated calendar color")
                else:
                    ctx.send("Calendar Bot already knows this Calendar-ID is associated with this channel")
            else:
                saved_channel["display"][calendarid] = {"name": cal_name, "color": color}
        else:  # channel is known but no display section yet.
            data[channel]["display"] = {}
            data[channel]["display"][calendarid] = {"name": cal_name, "color": color}
    else:
        data[channel] = {}
        data[channel]["display"] = {}
        data[channel]["display"][calendarid] = {"name": cal_name,
                                                "color": color}  # this is the first calendar id for this channel

    # saving channels and their associated calendar ids in a json file
    print("writing json ", json)
    with open(saved_calendar_path, 'w') as f:
        json.dump(data, f)
    return data[channel]["display"]


def saveAutoDisplayWeekday(ctx, channel: str, weekday: int):
    if os.path.exists(saved_calendar_path):
        f = open(saved_calendar_path)
        data = json.load(f)
        f.close()
    else:
        data = {}

    if channel in data:
        saved_channel = data[channel]
        saved_channel["autoDisplayTable"] = weekday

    print("writing json ", json)
    with open(saved_calendar_path, 'w') as f:
        json.dump(data, f)
    return data[channel]["autoDisplayTable"]


def cnt_loop():
    while (True):
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

                        if (
                                expiration_seconds - time.time() <= 28800):  # if expiration time is reached in 8 or less hours
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
            if 'autoDisplayTable' in channeldata:
                displayWeekDay = channeldata['autoDisplayTable']
                today = datetime.datetime.today()
                if today.isoweekday() == displayWeekDay and today.hour < 12:  # 1= Monday, 2 = Tuesday, 3 ...
                    # should show table at some time between 0 and 8 o'clock
                    print(f"trigger auto show for channel {channel}")
                    asyncio.run_coroutine_threadsafe(showDays(None, {"show"}, asImage=True, channelid=int(channel)),
                                                     bot.loop)

        time.sleep(28600)  # wait for 8 hours

        # check all watched calendars and renew their notification channels

        # check auto display times


def start_cnt_Thread():
    t = threading.Thread(name="count", target=cnt_loop, daemon=True)
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


@app.get("/", status_code=200)  # http://localhost:8002/
async def root():
    return {"received"}


# https://developers.google.com/calendar/api/guides/push
@app.post("/callback", status_code=200)
async def callback(X_Goog_Channel_ID: Annotated[Union[str, None], Header()] = None,
                   X_Goog_Channel_Token: Annotated[Union[str, None], Header()] = None,
                   X_Goog_Channel_Expiration: Annotated[Union[str, None], Header()] = None,
                   X_Goog_Resource_ID: Annotated[Union[str, None], Header()] = None,
                   X_Goog_Resource_URI: Annotated[Union[str, None], Header()] = None,
                   X_Goog_Resource_State: Annotated[Union[str, None], Header()] = None,
                   X_Goog_Message_Number: Annotated[Union[str, None], Header()] = None):
    asyncio.run_coroutine_threadsafe(
        new_event_creation_callback_display(X_Goog_Resource_URI, X_Goog_Channel_Expiration, X_Goog_Channel_Token,
                                            X_Goog_Channel_ID), bot.loop)
    print("google notification for", X_Goog_Resource_URI, "expiration data", X_Goog_Channel_Expiration, "for channel",
          X_Goog_Channel_Token, "; notification channel id:", X_Goog_Channel_ID)
    return {"received"}


def startCallbackServerThread():
    print("starting watch callback thread")
    t = threading.Thread(name="watchCallback", target=start)
    t.setDaemon(True)
    t.start()


def start():
    uvicorn.run(app, host="0.0.0.0", port=8002)


startCallbackServerThread()
start_cnt_Thread()
bot.run(DISCORD_BOT_TOKEN)
