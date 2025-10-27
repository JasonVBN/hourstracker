from flask import Blueprint, session, render_template, redirect, request
from db import *
from datetime import datetime
from log import log

entries_bp = Blueprint('entries', __name__)

@entries_bp.route('/entries/recon/<string:id>', methods=['POST'])
def recon_entry(id: str):
    if ('email' not in session) or ('userinfo' not in session):
        return redirect('/login')
    if session['userinfo'].get('role') != 'admin' or session['userinfo'].get('status') != 'approved':
        return render_template("badboi.html")
    
    runquery("UPDATE entries SET status = 'pending' WHERE id = %s",
                (id,))
    log(f'entry {id} marked for reconsideration by {session.get("email")}')
    auditlog(f"{session['userinfo']['fname']} {session['userinfo']['lname']} set entry ID: {id} back to pending")
    return {"msg": "Successfully set back to pending"}, 200

@entries_bp.route('/entries/delete/<string:id>', methods=['POST'])
def delete_entry(id: str):
    if ('email' not in session) or ('userinfo' not in session):
        return redirect('/login')
    if session['userinfo'].get('role') != 'admin' or session['userinfo'].get('status') != 'approved':
        return render_template("badboi.html")
    
    runquery("DELETE FROM entries WHERE id = %s", (id,))
    log(f'entry {id} deleted by {session.get("email")}')
    auditlog(f"{session['userinfo']['fname']} {session['userinfo']['lname']} deleted entry ID {id}")
    return {}, 200
