from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv
import os
import asyncio

load_dotenv()

# Fix for Python 3.14 asyncio loop issue
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

if not API_ID or not API_HASH:
    print("❌ Please make sure API_ID and API_HASH are set in your .env file!")
    exit(1)

print("Starting session generator...")
print("Please enter your phone number and the OTP when prompted.")
with TelegramClient(StringSession(), API_ID, API_HASH) as client:
    print("\n\n✅ Your String Session was successfully generated!\n")
    print("⚠️ COPY THE LONG STRING BELOW ⚠️")
    print("Add it to Render Environment Variables with the key: SESSION_STRING\n")
    print("-" * 50)
    print(client.session.save())
    print("-" * 50)
    print("\n")
