from flask import Blueprint, session, render_template, redirect, send_file
import openpyxl
from db import *
import io

export_bp = Blueprint('export', __name__)

@export_bp.route('/export')
def exportpage():
    if ('email' not in session) or ('userinfo' not in session):
        return redirect('/login')
    if session['userinfo'].get('role') != 'admin' or session['userinfo'].get('status') != 'approved':
        return render_template("badboi.html")
    
    return render_template('export.html')

@export_bp.route('/export/xlsx')
def exportxlsx():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"

    events = runquery('''SELECT id, name, date
                      FROM events''')

    columnidx = {}
    r1 = ["First Name", "Last Name", "Student ID", "Email", "TOTAL HOURS"]
    r2 = ["", "", "", "", ""]
    for ev in events:
        r1.append(ev['name'])
        r2.append(ev['date'])
        columnidx[ev['id']] = len(r1) - 1  # Store the index of the event in the header row
    ws.append(r1)
    ws.append(r2)
    users = runquery('''SELECT id, fname, lname, sid, email FROM users''')

    data = {u['id'] : [u['fname'], u['lname'], u['sid'], u['email'], 0] + [0]*len(events) for u in users}
    # userid : [fname, lname, sid, email, ...]
    print(data)
    entries = runquery('''
                       SELECT * FROM entries 
                       WHERE status="approved"
                       ''')
    # optimize: only select needed fields
    
    for en in entries:
        uid = en['user_id']
        event_id = en['event_id']
        data[uid][4] += en['hours']
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
