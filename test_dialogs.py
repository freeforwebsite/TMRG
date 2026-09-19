import asyncio
from telethon import TelegramClient
client=TelegramClient('movie_assistant_2', 36869346, '9abc474ef05c5e46b2210b02eb4c81fc')
async def main():
    await client.start()
    async for dialog in client.iter_dialogs():
        print(f'{dialog.name}: {dialog.id}')
client.loop.run_until_complete(main())
