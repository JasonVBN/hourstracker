from flask import Blueprint, session, render_template, redirect, request
from db import *
from log import log

profile_bp = Blueprint('profile', __name__)

MAX_SIZE = 4 * 1024 * 1024  # 4 MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

@profile_bp.route('/profile/changepfp', methods=['POST'])
def changepfp():
    print(dict(request.files))
    imgfile = request.files.get('pfp-upload')
    print(f"{imgfile} \n {imgfile.filename}  {imgfile.mimetype}  {imgfile.content_length}")
    if imgfile:
        print("[profile/changepfp] Received pfp upload")
        if imgfile.content_length > MAX_SIZE:
            return {"msg": "File too large (max of 4MB)"}, 400
        exten = imgfile.filename.split('.')[-1]
        fname = f'static/pfps/{session["userinfo"]["id"]}.{exten}'
        imgfile.save(fname)
        runquery("""UPDATE users SET pfp = %s WHERE email = %s""", 
                 ('/'+fname, session['email']))
        log(f'Profile picture changed by {session.get("email")}')
        
        return {"msg": "Success"}, 200
    return {"msg": "No file uploaded"}, 400
