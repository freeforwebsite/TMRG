# Telegram Movie Assistant (Userbot)

A Python Telethon-based userbot that runs on a dedicated Telegram account to act as a movie-request assistant in a specific group. 

## Features
- Listens to movie requests in a target group.
- Fuzzy matches requests against a local SQLite database.
- Replies with the exact movie file if found.
- Asks for clarification if multiple matches are found.
- Admin commands to add, remove, and manage the database.
- Async, rate-limited, and duplicate-request protected.

## Prerequisites
- Python 3.8+
- A dedicated Telegram account (do not use your personal account if you want this to run independently).
- API ID and API Hash from [my.telegram.org](https://my.telegram.org).

## Setup Instructions

1. **Clone or Extract the Project**
   Navigate to the project directory.

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**
   Rename `.env.example` to `.env` and fill in your details:
   - `API_ID`: Your Telegram API ID.
   - `API_HASH`: Your Telegram API Hash.
   - `SESSION_NAME`: The name of the session file (e.g., `movie_assistant`).
   - `ADMIN_IDS`: Comma-separated list of admin Telegram User IDs.
   - `TARGET_GROUP_ID`: The Telegram Chat ID of the group where the bot should listen for requests. (Remember that supergroups often start with `-100`).

4. **Prepare the Dedicated Account**
   - Log into your dedicated Telegram account on your phone/desktop.
   - Set the Custom display name, Profile picture, and Username as desired.
   - Join the target group with this dedicated account.

5. **First Run (Authentication)**
   Run the bot for the first time to authenticate the session:
   ```bash
   python main.py
   ```
   - You will be prompted to enter the phone number of the dedicated account.
   - Enter the OTP code sent to that Telegram account.
   - A `.session` file will be created. You won't need to log in again unless the session is revoked.

## Admin Commands

Only users listed in `ADMIN_IDS` can use these commands. You can send these commands in any chat with the bot, or in the group (though a private chat with the bot is recommended to keep the group clean).

- `/addmovie Title | Year | Language | Quality | Size` 
  *(Must be sent as a **reply** to a movie file/message)*
  Example: `/addmovie Interstellar | 2014 | English | 1080p | 2.5GB`
- `/removemovie <id>` - Remove a movie by its database ID.
- `/search <query>` - Search the database for movies.
- `/stats` - View database statistics.

## Disclaimer
Ensure you only distribute movies/files that you own or have permission to distribute, including public-domain or authorized content. Do not distribute unauthorized copyrighted files.
