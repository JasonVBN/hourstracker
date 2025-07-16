import smtplib
from email.message import EmailMessage
import os
from dotenv import load_dotenv
load_dotenv()

def send_email(to_addr, subject, content):
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = "abcdef13566@gmail.com"
    msg['To'] = to_addr
    msg.set_content(content)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login("abcdef13566@gmail.com", os.getenv('EMAIL_APP_PASS'))
        smtp.send_message(msg)
