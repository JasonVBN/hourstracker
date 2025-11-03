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
    today = datetime.now(TIMEZONE).date()
    print(today)
    yday = today - timedelta(days=1)
    yday_pts = calculate_points(session.get('email'), yday)
    return render_template('greed.html',
                           today=today,
        user=session.get('userinfo'),
        yday_pts=round(yday_pts,2),
        )

@greed_bp.route('/greed/submit', methods=['POST'])
def submit():
    if 'email' not in session:
        return {"msg": "Must be logged in to play"}, 403
    
    # Get the user's pick from the form
    user_pick = request.form.get('pick')
    dt_now = datetime.now(TIMEZONE)
    print(dt_now)
    with open('greedsubs.csv', 'a') as f:
        writer = csv.writer(f)
        writer.writerow([session['email'], user_pick, 
                         time.time(), dt_now.strftime("%Y-%m-%d %H:%M")])
    return {"msg": "Submission recorded"}, 200

def calculate_points(target_email: str, date):
    date_str = date.strftime('%Y-%m-%d')
    with open('greedsubs.csv', 'r') as f:
        reader = csv.reader(f)
        next(reader) #skip header line
        freqs = {} # pick -> count
        mypick = -1
        for row in reader:
            email = row[0]
            pick = int(row[1])
            dt = row[3].strip()
            if dt.startswith(date_str):
                freqs[pick] = freqs.get(pick,0) + 1
                if email == target_email:
                    mypick = pick
        if mypick == -1: return 0
        else: 
            return mypick / freqs[mypick]
