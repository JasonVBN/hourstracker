from flask import Blueprint, session, render_template, redirect, request
from db import *
import time
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from log import log
import csv

greed_bp = Blueprint('greed', __name__)

TIMEZONE = ZoneInfo('America/Chicago')

@greed_bp.route('/greed')
def greed():
    try:
        today = datetime.now(TIMEZONE).date()
        today_sub = get_sub(session.get('email'), today)
        yday = today - timedelta(days=1)
        yday_pts = calculate_points(session.get('email'), yday)
        return render_template('greed.html',
                            today=today,
                            today_sub=today_sub,
            user=session.get('userinfo'),
            yday_pts=round(yday_pts,2),
            )
    except Exception as e:
        log(f"ERROR: {e}")
        return render_template('error.html', error=str(e))

@greed_bp.route('/greed/submit', methods=['POST'])
def submit():
    if 'email' not in session:
        return {"msg": "Must be logged in to play"}, 403
    
    try:
        # Get the user's pick from the form
        user_pick = int(request.form.get('pick'))
        dt_now = datetime.now(TIMEZONE)
        print(dt_now)
        with open('greedsubs.csv', 'a') as f:
            writer = csv.writer(f)
            writer.writerow([session['email'], user_pick, 
                            time.time(), dt_now.strftime("%Y-%m-%d %H:%M")])
        return {"msg": "Submission recorded!"}, 200
    except Exception as e:
        return {"msg": f"{e}"}, 500

def calculate_points(target_email: str, date):
    date_str = date.strftime('%Y-%m-%d')
    with open('greedsubs.csv', 'r') as f:
        reader = csv.reader(f)
        next(reader) #skip header line
        freqs = {} # pick -> count
        mypick = -1
        for row in reader:
            try:
                email = row[0]
                pick = int(row[1])
                dt = row[3].strip()
            except:
                continue
            if dt.startswith(date_str):
                freqs[pick] = freqs.get(pick,0) + 1
                if email == target_email:
                    mypick = pick
        if mypick == -1: return 0
        else: 
            return mypick / freqs[mypick]

def get_sub(target_email: str, date: date):
    '''gets submission by target_email on specific date, or 0'''
    if not target_email: return 0

    date_str = date.strftime('%Y-%m-%d')
    with open('greedsubs.csv', 'r') as f:
        reader = csv.reader(f)
        next(reader) #skip header line
        for row in reader:
            try:
                email = row[0]
                pick = int(row[1])
                dt = row[3].strip()
            except:
                continue
            if dt.startswith(date_str) and email == target_email:
                return pick
    return 0
