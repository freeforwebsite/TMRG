import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import API_ID, API_HASH, SESSION_NAME

async def main():
    print(f"Reading existing session: {SESSION_NAME}.session")
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.connect()
    
    if await client.is_user_authorized():
        # Map the SQLite keys to a new StringSession
        string_s = StringSession()
        string_s.set_dc(client.session.dc_id, client.session.server_address, client.session.port)
        string_s.auth_key = client.session.auth_key
        
        extracted_string = string_s.save()
        
        print("\n" + "="*50)
        print("SUCCESS! Here is the StringSession extracted from your existing login:\n")
        print(extracted_string)
        print("\n" + "="*50)
    else:
        print("\nFAILED: This session is not currently logged in.")
        
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
