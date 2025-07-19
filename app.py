from flask import (Flask, render_template, redirect, url_for, jsonify,
                   session, request, send_file, make_response)
from authlib.integrations.flask_client import OAuth
from db import *
from qr import *
from emailer import send_email
import jwt
import requests
import io
from dotenv import load_dotenv
import os
load_dotenv()

CLIENT_ID = os.getenv('COGNITO_CLIENT_ID')

app = Flask(__name__)
oauth = OAuth(app)
app.secret_key = 'hi'

oauth.register(
  name='oidc',
  authority='https://cognito-idp.us-east-2.amazonaws.com/us-east-2_qYsEPt2KR',
  client_id=CLIENT_ID,
  client_secret=os.getenv('COGNITO_CLIENT_SECRET'),
  server_metadata_url='https://cognito-idp.us-east-2.amazonaws.com/us-east-2_qYsEPt2KR/.well-known/openid-configuration',
  client_kwargs={'scope': 'openid email'}
)

@app.route('/')
def index():
    
    return render_template('index.html',
                           user=session.get('userinfo'),
                           allusers=getallusers(),
                           events=getallevents()
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
    runquery("UPDATE admins SET status = 'denied' WHERE id = %s", (id,))
    email = runquery("SELECT email FROM admins WHERE id = %s", (id,))[0]['email']
    send_email(email,
        "you've been kicked",
        """you've been kicked from the admin list
        (this is an automated message, but you can still reply)""")
    return redirect('/')

@app.route('/entry', methods=['POST'])
def entry():
    event_id = request.form.get('event_id')
    name = request.form.get('name')
    sid = request.form.get('sid')

    mimetype, data = None, None
    file = request.files.get('proofdoc')
    if file:
        filename = (file.filename)
        mimetype = file.mimetype
        data = file.read()
        print("mimetype:", mimetype)

    runquery("INSERT INTO entries (event_id, name, sid, status, proof, mimetype) " \
                "VALUES (%s, %s, %s, 'pending', %s, %s)",
                (event_id, name, sid, data, mimetype))
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
    pending_list = runquery("""SELECT entries.*,
                            events.name AS event_name, events.date, events.hours
                            FROM entries
                            JOIN events ON entries.event_id = events.id
                            WHERE status = 'pending'""")
    print(pending_list)
    return render_template('entries.html',
            entries=pending_list,
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

@app.route('/query', methods=['POST'])
def query():
    res = runquery('''SELECT entries.status,
             events.name, events.date, events.hours
             FROM entries
             JOIN events ON entries.event_id = events.id
             WHERE sid = %s''',
             (request.form.get('sid'),))
    totals = runquery('''SELECT status, SUM(events.hours) as total
                      FROM entries
                      JOIN events ON entries.event_id = events.id
                      WHERE sid = %s
                      GROUP BY status''',
             (request.form.get('sid'),))
    return render_template('index.html',
                           user=session.get('userinfo'),
                           allusers=getallusers(),
                           events=getallevents(),
                           queryresults=res,
                           totals={x['status']: x['total'] for x in totals}
                           )

@app.route('/events')
def events():
    return render_template('events.html',
                           events=getallevents(),
    )

@app.route('/events/new', methods=['POST'])
def new_event():
    name = request.form.get('event_name')
    hours = int(request.form.get('hours') or 0)
    date = request.form.get('date') or None
    desc = request.form.get('desc') or None
    needproof = request.form.get('needproof')

    addevent(name, hours, date, desc, needproof)
    return redirect('/events')

# @app.route('/events/qr/<int:event_id>')
# def getqr(event_id: int):
#     # return 'hello'
#     qrlink = f"https://hourswizard.com:5000/checkin/{event_id}"
#     img = make_qr(qrlink)

#     buf = io.BytesIO()
#     img.save(buf, format='PNG')
#     buf.seek(0)
#     return send_file(buf, mimetype='image/png',)

@app.route('/admin/accept/<int:id>')
def accept(id: int):
    print(f"[app/accept] Accepting admin request for ID: {id}")
    updatestatus(id, 'approved')

    email = runquery("SELECT email FROM admins WHERE id = %s", (id,))[0]['email']
    send_email(email,
        "you've been approved",
        """you've been approved as an admin!
        (this is an automated message, but you can still reply)""")
    return redirect('/')

@app.route('/admin/deny/<int:id>')
def deny(id: int):
    print(f"[app/accept] Denying admin request for ID: {id}")
    updatestatus(id, 'denied')

    email = runquery("SELECT email FROM admins WHERE id = %s", (id,))[0]['email']
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

@app.route('/login')
def login():
    redirect_uri = url_for('authorize', _external=True)
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
    logout_url = ( "https://us-east-2qYsEPt2KR.auth.us-east-2.amazoncognito.com/logout"
    f"?client_id={CLIENT_ID}"
    f"&logout_uri={os.getenv('INDEX_URL')}" )

    return redirect(logout_url)

if __name__ == '__main__':
    app.run(port=5000, 
            host='0.0.0.0',
            debug=True,
            # ssl_context='adhoc',
            ssl_context=(os.getenv('CERT_PATH'),
                         os.getenv('KEY_PATH'))
            )
