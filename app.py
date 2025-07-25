from flask import (Flask, render_template, redirect, url_for, jsonify,
                   session, request, send_file, make_response)
from authlib.integrations.flask_client import OAuth
from db import *
from qr import *
from emailer import send_email
import jwt
import requests
import io
import openpyxl
from datetime import datetime
import time
from dotenv import load_dotenv
import os
load_dotenv()

CLIENT_ID = os.getenv('COGNITO_CLIENT_ID')

app = Flask(__name__)
oauth = OAuth(app)
app.secret_key = 'hi'

oauth.register(
  name='oidc',
  authority=os.getenv('IDP_ENDPOINT'),
  client_id=CLIENT_ID,
  client_secret=os.getenv('COGNITO_CLIENT_SECRET'),
  server_metadata_url=f'{os.getenv("IDP_ENDPOINT")}/.well-known/openid-configuration',
  client_kwargs={'scope': 'openid email'}
)

def log(msg):
    with open('log.txt', 'a') as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {msg}\n")

@app.route('/')
def index():
    log(f'index visited from {request.remote_addr}')
    log(session)

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
@app.route('/checkin/<int:event_id>')
def checkin(event_id):
    return render_template('checkin.html',
                            event=geteventbyid(event_id),
    )

@app.route('/admin/request')
def adminrequest():
    return render_template('askname.html')

@app.route('/admin/kick/<int:id>')
def kick(id: int):
    runquery("UPDATE users SET status = 'denied' WHERE id = %s", (id,))
    email = runquery("SELECT email FROM users WHERE id = %s", (id,))[0]['email']
    send_email(email,
        "you've been kicked",
        """you've been kicked from the admin list
        (this is an automated message, but you can still reply)""")
    return redirect('/')

@app.route('/entry', methods=['POST'])
def entry():
    event_id = request.form.get('event_id')
    hours = request.form.get('hours')

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
                            users.name AS user_name, users.sid
                            FROM entries AS en
                            JOIN events ON en.event_id = events.id
                            JOIN users ON en.user_id = users.id
                            WHERE en.status = 'pending'""")
    past_list = runquery("""SELECT en.id, en.hours, en.mimetype, en.status,
                            events.name AS event_name, events.date,
                            users.name AS user_name, users.sid
                            FROM entries AS en
                            JOIN events ON en.event_id = events.id
                            JOIN users ON en.user_id = users.id
                            WHERE en.status != 'pending' """)
    t2 = time.time()
    return render_template('entries.html',
            pending_entries=pending_list,
            past_entries=past_list,
            time=round(t2-t1,3),
    )

@app.route('/entries/approve/<int:id>')
def approve_entry(id: int):
    print(f"[app/approve_entry] Approving entry ID: {id}")
    runquery("UPDATE entries SET status = 'approved' WHERE id = %s", (id,))
    return redirect('/entries/pending')

@app.route('/entries/deny/<int:id>')
def deny_entry(id: int):
    print(f"[app/deny_entry] Denying entry ID: {id}")
    runquery("UPDATE entries SET status = 'denied' WHERE id = %s", (id,))
    return redirect('/entries/pending')

# @app.route('/query', methods=['POST'])
# def query():
    
#     return render_template('index.html',
#                            user=session.get('userinfo'),
#                            allusers=getallusers(),
#                            events=getallevents(),
                           
#                            )

@app.route('/events')
def events():
    if ('email' not in session) or ('userinfo' not in session):
        return redirect('/login')
    if session['userinfo'].get('role') != 'admin' or session['userinfo'].get('status') != 'approved':
        return render_template("badboi.html")
    
    return render_template('events.html',
                           events=getallevents(),
    )

@app.route('/events/new', methods=['POST'])
def new_event():
    name = request.form.get('event_name')
    hours = float(request.form.get('hours') or 0)
    date = request.form.get('date') or None
    desc = request.form.get('desc') or None
    needproof = request.form.get('needproof') or 0

    addevent(name, hours, date, desc, needproof)
    return redirect('/events')

@app.route('/events/edit/<int:id>', methods=['POST'])
def edit_event(id: int):
    name = request.form.get('event_name')
    hours = float(request.form.get('hours') or 0)
    date = request.form.get('date') or None
    desc = request.form.get('desc') or None
    needproof = request.form.get('needproof') or 0

    print(f"[app/edit_event] Editing event ID: {id}")
    runquery("UPDATE events SET name = %s, hours = %s, date = %s, `desc` = %s, needproof = %s WHERE id = %s",
             (name, hours, date, desc, needproof, id))
    return redirect('/events')

@app.route('/admin/accept/<int:id>')
def accept(id: int):
    print(f"[app/accept] Accepting admin request for ID: {id}")
    updatestatus(id, 'approved')

    email = runquery("SELECT email FROM users WHERE id = %s", (id,))[0]['email']
    send_email(email,
        "you've been approved",
        """you've been approved as an admin!
        (this is an automated message, but you can still reply)""")
    return redirect('/')

@app.route('/admin/deny/<int:id>')
def deny(id: int):
    print(f"[app/accept] Denying admin request for ID: {id}")
    updatestatus(id, 'denied')

    email = runquery("SELECT email FROM users WHERE id = %s", (id,))[0]['email']
    send_email(email,
        "you've been denied",
        """you've been denied from admin role :(
        (this is an automated message, but you can still reply)""")
    return redirect('/')

@app.route('/admin/request/submit', methods=['POST'])
def adminrequestsubmit():
    name = request.form.get('name')
    sid = request.form.get('sid')

    # is it safe to assume user still logged in?
    addnewadmin(session['email'], name)
    userinfo = getuserinfo(session['email'])

    session['userinfo'] = userinfo
    print(f"User info after request: {session['userinfo']}")
    
    return redirect('/')

@app.route('/member/join/submit', methods=['POST'])
def memberjoin():
    fname = request.form.get('fname')
    lname = request.form.get('lname')
    sid = request.form.get('sid')

    if not (fname and lname and sid):
        return jsonify({"error": "All fields are required"}), 400

    # is it safe to assume user still logged in?
    runquery('''INSERT INTO users (email, name, sid, status, role) 
            VALUES (%s, %s, %s, 'approved', 'member')
            ON DUPLICATE KEY UPDATE
            name=VALUES(name), sid=VALUES(sid), status='approved', role='member' ''',
              (session['email'], f'{fname} {lname}', sid))
    
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
                           users=users)

@app.route('/export')
def exportpage():
    if ('email' not in session) or ('userinfo' not in session):
        return redirect('/login')
    if session['userinfo'].get('role') != 'admin' or session['userinfo'].get('status') != 'approved':
        return render_template("badboi.html")
    
    return render_template('export.html')

@app.route('/export/xlsx')
def exportxlsx():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"

    events = runquery('''SELECT id, name, date
                      FROM events''')

    columnidx = {}
    r1 = ["Name", "Student ID", "Email", "TOTAL HOURS"]
    r2 = ["", "", "", ""]
    for ev in events:
        r1.append(ev['name'])
        r2.append(ev['date'])
        columnidx[ev['id']] = len(r1) - 1  # Store the index of the event in the header row
    ws.append(r1)
    ws.append(r2)
    users = runquery('''SELECT id, name, sid, email FROM users''')

    data = {u['id'] : [u['name'], u['sid'], u['email'], 0] + [0]*len(events) for u in users}
    # userid : [name, sid, email, ...]

    entries = runquery('''
                       SELECT * FROM entries 
                       WHERE status="approved"
                       ''')
    # optimize: only select needed fields
    
    for en in entries:
        uid = en['user_id']
        event_id = en['event_id']
        data[uid][3] += en['hours']
        if event_id in columnidx:
            col_idx = columnidx[event_id]
            data[uid][col_idx] += en['hours']
    
    # write data to worksheet
    for uid in data:
        ws.append(['' if x==0 else x for x in data[uid]])

    # Save to BytesIO buffer
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="hoursdata.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route('/login')
def login():
    log(f'/login from {request.remote_addr}')
    # redirect_uri = url_for('authorize', _external=True)
    redirect_uri = os.getenv('INDEX_URL') + 'authorize'
    print(f'Redirect URI: {redirect_uri}')
    return oauth.oidc.authorize_redirect(redirect_uri)

@app.route('/authorize')
def authorize():
    token = oauth.oidc.authorize_access_token()
    id_token = token.get('id_token')
    print(f"ID Token: {id_token}")
    decoded = jwt.decode(id_token, options={"verify_signature": False})
    print(f"Decoded ID Token: {decoded}")

    session['email'] = token['userinfo'].get('email')
    session['userinfo'] = getuserinfo(session['email'])

    # getting name
    # userinfo_url = 'https://us-east-2qysept2kr.auth.us-east-2.amazoncognito.com/oauth2/userInfo'
    # access_token = token['access_token']
    # headers = {
    #     'Authorization': f"Bearer {access_token}"
    # }
    # resp = requests.get(userinfo_url, headers=headers)
    # print('request response:', resp.json())

    print(session['userinfo'])

    if session['userinfo'] is None:
        return redirect('/admin/request')
    else:
        return redirect('/')

@app.route('/logout')
def logout():
    session.clear()
    logout_url = ( "https://us-east-25urYVuNOR.auth.us-east-2.amazoncognito.com/logout"
    f"?client_id={CLIENT_ID}"
    f"&logout_uri={os.getenv('INDEX_URL')}" )

    return redirect(logout_url)

@app.route('/profile')
def myprofile():
    return render_template('profile.html')

@app.route('/profile/editbio', methods=['POST'])
def editbio():
    new_bio = request.form.get('bio')
    runquery("UPDATE users SET bio = %s WHERE email = %s", 
             (new_bio, session['email']))
    session['userinfo'] = getuserinfo(session['email'])
    return redirect('/profile')

@app.route('/profile/<int:id>')
def profile(id: int):
    user = runquery("SELECT name,bio FROM users WHERE id = %s", (id,))[0]
    return render_template('profile-other.html', 
                           name=user['name'],
                           bio=user['bio'],
    )

if __name__ == '__main__':
    app.run(port=5000, 
            host='0.0.0.0',
            debug=True,
            # ssl_context='adhoc',
            # ssl_context=(os.getenv('CERT_PATH'),
            #              os.getenv('KEY_PATH'))
            )
