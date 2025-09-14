from flask import (Flask, render_template, redirect, url_for, jsonify,
                   session, request, make_response, send_from_directory)
from routes.auth import auth_bp, oauth
from routes.export import export_bp
from db import *
# from qr import *
from emailer import send_email
import requests
import uuid
from log import log
import time
from dotenv import load_dotenv
import os
load_dotenv()

app = Flask(__name__)
app.register_blueprint(auth_bp)
app.register_blueprint(export_bp)
app.secret_key = 'hi'
oauth.init_app(app)


@app.route('/')
def index():
    log(f"""index visited from {request.headers.get('X-Forwarded-For')}
    {session}""")

    res, totals = [], []
    if 'email' in session:
        session['userinfo'] = getuserinfo(session['email'])
        if session['userinfo'] is None:
            return redirect('/admin/request')

        res = runquery('''SELECT entries.status, entries.hours,
                events.name, events.date
                FROM entries
                JOIN events ON entries.event_id = events.id
                WHERE user_id = %s''',
             (session['userinfo']['id'],))
        totals = runquery('''SELECT status, SUM(entries.hours) as total
                      FROM entries
                      JOIN events ON entries.event_id = events.id
                      WHERE user_id = %s
                      GROUP BY status''',
             (session['userinfo']['id'],))
    
    return render_template('index.html',
                           user=session.get('userinfo'),
                           allusers=getallusers(),
                           events=getallevents(),
                           queryresults=res,
                           totals={x['status']: x['total'] for x in totals}
    )

# visited only via QR code
@app.route('/checkin/<string:event_id>')
def checkin(event_id):
    if 'email' not in session or 'userinfo' not in session:
        session['checkin_event_id'] = event_id

        log(f"login from {request.headers.get('X-Forwarded-For')} (redirect to /checkin)")
        redirect_uri = os.getenv('INDEX_URL') + 'checkin'
        print(f'Redirect URI: {redirect_uri}')
        return oauth.oidc.authorize_redirect(redirect_uri) # redirect to /checkin
    return render_template('checkin.html',
                            event=geteventbyid(event_id),
                            user=session.get('userinfo')
    )

@app.route('/checkin')
def checkin_gen():
    token = oauth.oidc.authorize_access_token()

    session['email'] = token['userinfo'].get('email')
    session['userinfo'] = getuserinfo(session['email'])

    if 'checkin_event_id' not in session:
        return redirect('/')
    event_id = session['checkin_event_id']
    return redirect(f'/checkin/{event_id}' if event_id else '/')

@app.route('/admin/request')
def adminrequest():
    return render_template('askname.html')

@app.route('/admin/kick/<int:id>')
def kick(id: int):
    runquery("UPDATE users SET status = 'denied' WHERE id = %s", (id,))
    info = runquery("SELECT email, fname, lname FROM users WHERE id = %s", (id,))[0]
    send_email(info['email'],
        "you've been kicked",
        """you've been kicked from the admin list
        (this is an automated message, but you can still reply)""")
    auditlog(f"{session['userinfo']['fname']} {session['userinfo']['lname']} kicked admin {info['fname']} {info['lname']}")
    return redirect('/')

@app.route('/entry', methods=['POST'])
def entry():
    event_id = request.form.get('event_id')
    hours = request.form.get('hours') or 0

    mimetype, data = None, None
    file = request.files.get('proofdoc')
    if file:
        filename = (file.filename)
        mimetype = file.mimetype
        data = file.read()
        print("mimetype:", mimetype)

    runquery("INSERT INTO entries (event_id, user_id, hours, proof, mimetype, status) " \
                "VALUES (%s, %s, %s, %s, %s, 'pending')",
                (event_id, session['userinfo']['id'], hours, data, mimetype))
    return redirect('/')

@app.route('/entry/proof/<int:id>')
def entry_proof(id: int):
    dik = runquery("SELECT proof, mimetype " \
        "FROM entries WHERE id= %s", (id,))[0]
    data,mimetype = dik['proof'],dik['mimetype']
    print(mimetype)
    response = make_response(data)
    response.headers.set('Content-Type', mimetype)
    response.headers.set('Content-Disposition', 'inline', filename=f'proof-{id}')
    return response

@app.route('/entries/pending')
def pending_entries():
    if ('email' not in session) or ('userinfo' not in session):
        return redirect('/login')
    if session['userinfo'].get('role') != 'admin' or session['userinfo'].get('status') != 'approved':
        return render_template("badboi.html")
    
    t1 = time.time()
    pending_list = runquery("""SELECT en.id, en.hours, en.mimetype, en.status,
                            events.name AS event_name, events.date,
                            users.fname AS user_fname, users.lname AS user_lname, users.sid
                            FROM entries AS en
                            JOIN events ON en.event_id = events.id
                            JOIN users ON en.user_id = users.id
                            WHERE en.status = 'pending'""")
    past_list = runquery("""SELECT en.id, en.hours, en.mimetype, en.status,
                            events.name AS event_name, events.date,
                            users.fname AS user_fname, users.lname AS user_lname, users.sid
                            FROM entries AS en
                            JOIN events ON en.event_id = events.id
                            JOIN users ON en.user_id = users.id
                            WHERE en.status != 'pending' """)
    t2 = time.time()
    log(f'entries page visited by {session.get("email")}')
    return render_template('entries.html',
            pending_entries=pending_list,
            past_entries=past_list,
            time=round(t2-t1,3),
    )

@app.route('/entries/approve/<int:id>')
def approve_entry(id: int):
    print(f"[app/approve_entry] Approving entry ID: {id}")
    runquery("UPDATE entries SET status = 'approved' WHERE id = %s", (id,))
    
    info = runquery("""SELECT hours, users.email, users.notifs 
                FROM entries
                JOIN users ON users.id = entries.user_id
                WHERE entries.id = %s""", (id,))[0]
    if info['notifs']:
        send_email(info['email'],
            "Submission approved",
            f"""Your entry of {info['hours']} hours has been approved!
            (this is an automated message, but you can still reply)""")
    return redirect('/entries/pending')

@app.route('/entries/deny/<int:id>')
def deny_entry(id: int):
    print(f"[app/deny_entry] Denying entry ID: {id}")
    runquery("UPDATE entries SET status = 'denied' WHERE id = %s", (id,))

    info = runquery("""SELECT hours, users.email, users.notifs 
                FROM entries
                JOIN users ON users.id = entries.user_id
                WHERE entries.id = %s""", (id,))[0]
    if info['notifs']:
        send_email(info['email'],
            "Submission denied",
            f"""Your entry of {info['hours']} hours has been denied :(
            (this is an automated message, but you can still reply)""")
    return redirect('/entries/pending')

@app.route('/events')
def events():
    if ('email' not in session) or ('userinfo' not in session):
        return redirect('/login')
    if session['userinfo'].get('role') != 'admin' or session['userinfo'].get('status') != 'approved':
        return render_template("badboi.html")
    
    log(f'events page visited by {session.get("email")}')
    return render_template('events.html',
                           events=getallevents(),
    )

@app.route('/events/new', methods=['POST'])
def new_event():
    name = request.form.get('event_name')
    code = request.form.get('code') or None
    hours = float(request.form.get('hours') or 0)
    date = request.form.get('date') or None
    desc = request.form.get('desc') or None
    needproof = request.form.get('needproof') or 0
    if not code:
        code = str(uuid.uuid4())
    addevent(code, name, hours, date, desc, needproof)
    log(f'new event created by {session.get("email")}')
    auditlog(f"{session['userinfo']['fname']} {session['userinfo']['lname']} created event: {name}")
    return redirect('/events')

@app.route('/events/edit/<string:id>', methods=['POST'])
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

@app.route('/events/delete/<string:id>', methods=['POST'])
def delete_event(id: str):
    print(f"[app/delete_event] Deleting event ID: {id}")
    name = runquery("SELECT name FROM events WHERE id = %s", (id,))[0]['name']
    runquery("DELETE FROM entries WHERE event_id = %s", (id,))
    runquery("DELETE FROM events WHERE id = %s", (id,))
    auditlog(f"{session['userinfo']['fname']} {session['userinfo']['lname']} deleted event: {name}")
    return {}, 200

@app.route('/admin/accept/<int:id>')
def accept(id: int):
    print(f"[app/accept] Accepting admin request for ID: {id}")
    updatestatus(id, 'approved')

    info = runquery("SELECT email, fname, lname FROM users WHERE id = %s", (id,))[0]
    send_email(info['email'],
        "you've been approved",
        """you've been approved as an admin!
        (this is an automated message, but you can still reply)""")
    auditlog(f"{session['userinfo']['fname']} {session['userinfo']['lname']} accepted {info['fname']} {info['lname']}'s admin request")
    return redirect('/')

@app.route('/admin/deny/<int:id>')
def deny(id: int):
    print(f"[app/accept] Denying admin request for ID: {id}")
    updatestatus(id, 'denied')

    info = runquery("SELECT email, fname, lname FROM users WHERE id = %s", (id,))[0]
    send_email(info['email'],
        "you've been denied",
        """you've been denied from admin role :(
        (this is an automated message, but you can still reply)""")
    auditlog(f"{session['userinfo']['fname']} {session['userinfo']['lname']} denied {info['fname']} {info['lname']}'s admin request")
    return redirect('/')

@app.route('/admin/request/submit', methods=['POST'])
def adminrequestsubmit():
    fname = request.form.get('fname')
    lname = request.form.get('lname')
    sid = request.form.get('sid')

    # is it safe to assume user still logged in?
    addnewadmin(session['email'], fname, lname, sid)
    userinfo = getuserinfo(session['email'])

    session['userinfo'] = userinfo
    print(f"User info after request: {session['userinfo']}")
    
    auditlog(f"{fname} {lname} requested admin role")
    return redirect('/')

@app.route('/member/join/submit', methods=['POST'])
def memberjoin():
    fname = request.form.get('fname')
    lname = request.form.get('lname')
    sid = request.form.get('sid')

    if not (fname and lname and sid):
        return jsonify({"error": "All fields are required"}), 400

    # is it safe to assume user still logged in?
    runquery('''INSERT INTO users (email, fname, lname, sid, status, role) 
            VALUES (%s, %s, %s, %s, 'approved', 'member')
            ON DUPLICATE KEY UPDATE
            fname=VALUES(fname), lname=VALUES(lname), sid=VALUES(sid), status='approved', role='member' ''',
              (session['email'], fname, lname, sid))

    userinfo = getuserinfo(session['email'])
    session['userinfo'] = userinfo
    print(f"User info after join: {session['userinfo']}")
    
    return redirect('/')

@app.route('/roster')
def roster():
    if ('email' not in session) or ('userinfo' not in session):
        return redirect('/login')
    if session['userinfo'].get('role') != 'admin' or session['userinfo'].get('status') != 'approved':
        return render_template("badboi.html")

    users = runquery('''SELECT * FROM users''')
    return render_template('roster.html', 
                           users=users,
                           events=getallevents())

@app.route('/roster/addhours', methods=['POST'])
def addhours():
    data = request.get_json()
    event_id = data.get('event_id')
    user_ids = data.get('user_ids', [])
    hours = data.get('hours', 0)
    print(f"[app/addhours] Adding hours for event ID: {event_id} to users: {user_ids}")

    for uid in user_ids:
        runquery("""INSERT INTO entries (event_id, user_id, hours, status) 
                 VALUES (%s, %s, %s, 'approved')""",
                  (event_id, uid, hours))
    return jsonify({"success": True}), 200

@app.route('/roster/kick/<int:id>', methods=['POST'])
def kickmember(id: int):
    reason = request.json.get('reason')
    info = runquery("""SELECT email, fname, lname FROM users
             WHERE id = %s""", (id,))[0]
    runquery("""DELETE FROM entries WHERE user_id = %s""", (id,))
    runquery("""DELETE FROM users WHERE id = %s""", (id,))
    send_email(info['email'],
        "You've been removed",
        f"""You've been removed from the roster :(
        Reason: {reason if reason else 'No reason provided'}
        If you think this is a mistake, reply to this email or rejoin.
        (this is an automated message)""")
    auditlog(f"{session['userinfo']['fname']} {session['userinfo']['lname']} "
             f"kicked user {info['fname']} {info['lname']}")
    return jsonify({"success": True})

@app.route('/profile')
def myprofile():
    if 'userinfo' not in session:
        return redirect('/login')
    return render_template('profile.html')

@app.route('/profile/editbio', methods=['POST'])
def editbio():
    new_bio = request.form.get('bio')
    runquery("UPDATE users SET bio = %s WHERE email = %s", 
             (new_bio, session['email']))
    session['userinfo'] = getuserinfo(session['email'])
    return redirect('/profile')

@app.route('/profile/editnotif', methods=['POST'])
def editnotif():
    new_notif = request.json.get('notify')
    runquery("UPDATE users SET notifs = %s WHERE email = %s", 
             (new_notif, session['email']))
    session['userinfo'] = getuserinfo(session['email'])
    return jsonify({"success": True, "notify": new_notif})

@app.route('/profile/<int:id>')
def profile(id: int):
    user = runquery("SELECT fname,lname,bio FROM users WHERE id = %s", (id,))[0]
    return render_template('profile-other.html', 
                           name=user['fname']+' '+user['lname'],
                           bio=user['bio'],
    )

@app.route('/auditlog')
def alogpage():
    if ('email' not in session) or ('userinfo' not in session):
        return redirect('/login')
    if session['userinfo'].get('role') != 'admin' or session['userinfo'].get('status') != 'approved':
        return render_template("badboi.html")
    alog = runquery("""SELECT action, timestamp FROM log 
                    ORDER BY timestamp DESC""")
    return render_template('auditlog.html', alog=alog)

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/contact/submit', methods=['POST'])
def contactsub():
    name = request.form.get('name')
    msg = request.form.get('message')
    log(f"{name} submitted Contact form: {msg}")
    return redirect('/contact')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/ads.txt')
def ads():
    return send_from_directory('static', 'ads.txt')


if __name__ == '__main__':
    app.run(port=5000, 
            host='0.0.0.0',
            debug=True,
            # ssl_context='adhoc',
            # ssl_context=(os.getenv('CERT_PATH'),
            #              os.getenv('KEY_PATH'))
            )
