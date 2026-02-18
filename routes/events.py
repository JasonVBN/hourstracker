from flask import Blueprint, session, render_template, redirect, request
from db import *
from datetime import datetime
from log import log

events_bp = Blueprint('events', __name__)


@events_bp.route('/events', methods=['GET'])
def events():
    if ('email' not in session) or ('userinfo' not in session):
        return redirect('/login')
    if session['userinfo'].get('role') != 'admin' or session['userinfo'].get('status') != 'approved':
        return render_template("badboi.html")
    
    log(f'events page visited by {session.get("email")}')
    return render_template('events.html',
                           events=getallevents(),
    )

@events_bp.route('/events/new', methods=['POST'])
def new_event():
    name = request.form.get('event_name')
    code = request.form.get('code') or None
    hours = float(request.form.get('hours') or 0)
    date = request.form.get('date') or None
    desc = request.form.get('desc') or None
    needproof = request.form.get('needproof') or 0
    if code:
        if not all(c.isalnum() or c == '-' for c in code):
            return {'err': 'Event code must only have alphanumeric (a-z, 0-9) and -'}, 400
    else:
        code = shortuuid()
    addevent(code, name, hours, date, desc, needproof)
    log(f'new event created by {session.get("email")}')
    auditlog(f"{session['userinfo']['fname']} {session['userinfo']['lname']} created event: {name}")
    return {}, 200

@events_bp.route('/events/edit/<string:id>', methods=['POST'])
def edit_event(id: str):
    name = request.form.get('event_name')
    hours = float(request.form.get('hours') or 0)
    date = request.form.get('date') or None
    desc = request.form.get('desc') or None
    needproof = request.form.get('needproof') or 0

    print(f"[app/edit_event] Editing event ID: {id}")
    runquery("UPDATE events SET name = %s, hours = %s, date = %s, `desc` = %s, needproof = %s WHERE id = %s",
             (name, hours, date, desc, needproof, id))
    return redirect('/events')

@events_bp.route('/events/delete/<string:id>', methods=['POST'])
def delete_event(id: str):
    print(f"[app/delete_event] Deleting event ID: {id}")
    name = runquery("SELECT name FROM events WHERE id = %s", (id,))[0]['name']
    runquery("DELETE FROM entries WHERE event_id = %s", (id,))
    runquery("DELETE FROM events WHERE id = %s", (id,))
    auditlog(f"{session['userinfo']['fname']} {session['userinfo']['lname']} deleted event: {name}")
    return {}, 200
