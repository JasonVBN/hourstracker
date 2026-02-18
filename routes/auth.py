from flask import Blueprint, session, request, redirect
from authlib.integrations.flask_client import OAuth
import jwt
from db import *
from log import log
from dotenv import load_dotenv
import os
load_dotenv()

auth_bp = Blueprint('auth', __name__)

CLIENT_ID = os.getenv('COGNITO_CLIENT_ID')
oauth = OAuth()
oauth.register(
  name='oidc',
  authority=os.getenv('IDP_ENDPOINT'),
  client_id=CLIENT_ID,
  client_secret=os.getenv('COGNITO_CLIENT_SECRET'),
  server_metadata_url=f'{os.getenv("IDP_ENDPOINT")}/.well-known/openid-configuration',
  client_kwargs={'scope': 'openid email'}
)

@auth_bp.route('/login')
def login():
    log(f"/login from {request.headers.get('X-Forwarded-For')}")
    # redirect_uri = url_for('authorize', _external=True)
    redirect_uri = os.getenv('INDEX_URL') + 'authorize'
    print(f'Redirect URI: {redirect_uri}')
    return oauth.oidc.authorize_redirect(redirect_uri)

@auth_bp.route('/authorize')
def authorize():
    print("Returned state:", request.args.get('state'))
    print("Stored state:", session.get('_oauth2_state'))
    
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
        # new user (not in DB yet)
        # get info:
        return redirect('/admin/request')
    else:
        if (session.get('checkin_redirect', 0) and
                'checkin_event_id' in session):
            return redirect(f"/checkin/{session['checkin_event_id']}")
        return redirect('/')

@auth_bp.route('/logout')
def logout():
    session.clear()
    logout_url = ( "https://us-east-25urYVuNOR.auth.us-east-2.amazoncognito.com/logout"
    f"?client_id={CLIENT_ID}"
    f"&logout_uri={os.getenv('INDEX_URL')}" )

    return redirect(logout_url)