# Reap Holding Online Meet - Real V1

Backend + Database + Login + Branded Jitsi meeting portal.

## Features

- Login system
- Demo admin and user accounts
- SQLite database
- Schedule meetings
- Start instant meetings
- Join by Meeting ID
- Jitsi meeting room embedded inside the portal
- Meeting notes
- Meeting status: Scheduled / Live / Completed / Cancelled
- Admin dashboard
- Shared data across devices on the same deployed server
- No pip install required

## Demo Accounts

Admin:
admin@reapholding.com
admin123

User:
user@reapholding.com
user123

## Run Locally

Open CMD inside the project folder and run:

python server.py

Then open:

http://127.0.0.1:8005

## Railway Start Command

python server.py

Railway will provide PORT automatically.

## Important

Internet is required for the video meeting room because it loads Jitsi Meet.
For production, use HTTPS/domain like:

meet.reapholding.com
