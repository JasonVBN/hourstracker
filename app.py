from flask import Flask, render_template, redirect, url_for, session, request
from authlib.integrations.flask_client import OAuth
from db import *
import jwt
import requests
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

@app.route('/entry', methods=['POST'])
def entry():
    event_id = request.form.get('event_id')
    name = request.form.get('name')
    sid = request.form.get('sid')
    runquery("INSERT INTO entries (event_id, name, sid, status) " \
                "VALUES (%s, %s, %s, 'pending')",
                (event_id, name, sid))
    return redirect('/')

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
    print(f"[app/approve_entry] Approving entry ID: {id}")
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
    hours = int(request.form.get('event_hours'))
    date = request.form.get('event_date') or None
    desc = request.form.get('event_desc') or None

    addevent(name, hours, date, desc)
    return redirect('/events')

@app.route('/accept/<int:id>')
def accept(id: int):
    print(f"[app/accept] Accepting admin request for ID: {id}")
    updatestatus(id, 'approved')
    return redirect('/')

@app.route('/adminrequest', methods=['POST'])
def adminrequest():
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
        return render_template('askname.html')
    else:
        return redirect('/')

@app.route('/logout')
def logout():
    session.clear()
    logout_url = ( "https://us-east-2qYsEPt2KR.auth.us-east-2.amazoncognito.com/logout"
    f"?client_id={CLIENT_ID}"
    "&logout_uri=http://localhost:5001/" )

    return redirect(logout_url)

if __name__ == '__main__':
    app.run(port=5001, 
            host='0.0.0.0',
            debug=True,
            # ssl_context='adhoc',
            # ssl_context=('C:\\Users\\JasonN\\.ssh\\fullchain.pem', 
            #              'C:\\Users\\JasonN\\.ssh\\privkey.pem')
            )
