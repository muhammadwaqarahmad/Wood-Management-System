# Abdul Sattar Woods — Office Setup Guide (step by step)

This guide sets up the app on your office network so **5–6 PCs share one set of
data**. It assumes **no technical background** — every click is written out.

- **MAIN PC**: one computer that stays ON. It holds the shared database
  (PostgreSQL). It can also be used normally.
- **OTHER PCs**: run the app and connect to the MAIN PC over the office network.

> Tip: Do the whole **MAIN PC** section first and get it working before you touch
> the other PCs.

Two passwords you will create (write both on paper, keep safe):
1. **postgres password** — set while installing PostgreSQL (the master key).
2. **timber password** — the app's own database password (you choose it in A3).

They are different. You will need both.

---

# PART 1 — THE MAIN PC

## Step 1 — Find (and fix) the main PC's network address

Other PCs must always reach the main PC at the same address.

1. Press the **Windows key**, type **cmd**, press **Enter**. A black window opens.
2. Type this and press **Enter**:
   ```
   ipconfig
   ```
3. Look for **IPv4 Address** under your active connection (Ethernet or Wi-Fi).
   It looks like **`192.168.1.10`**. **Write it down** — call it the *MAIN PC
   address*. You'll use it on every other PC.

> Strongly recommended: ask whoever manages your router to **reserve this IP** for
> the main PC (a "DHCP reservation") so it never changes. If it changes later,
> the other PCs stop connecting until you update their address.

---

## Step 2 — Install PostgreSQL (the database) on the MAIN PC

1. Open a browser, go to **https://www.postgresql.org/download/windows/**, click
   **Download the installer**, and download the latest **PostgreSQL** (e.g.
   version **17**).
2. Run the downloaded file. Click **Next** through the screens. Keep the default
   install folder and default components.
3. When it asks for a **password for the database superuser (postgres)** — type a
   password and **write it down**. This is your **postgres password**.
4. When it asks for the **Port**, leave it as **5432**. Keep clicking **Next**,
   then **Finish**. If it offers "Stack Builder" at the end, you can **uncheck**
   it and finish.

---

## Step 3 — Create the app's database

Now we make an empty database for the app.

1. Press the **Windows key**, type **SQL Shell**, and open **SQL Shell (psql)**.
   A black window opens and asks a few questions. **Just press Enter** to accept
   each default until it asks for the password:
   ```
   Server [localhost]:       ← press Enter
   Database [postgres]:      ← press Enter
   Port [5432]:              ← press Enter
   Username [postgres]:      ← press Enter
   Password for user postgres: ← type your POSTGRES password, press Enter
   ```
   IMPORTANT: while you type the password, **nothing appears on screen** (no dots,
   no stars). That is normal — just type it and press **Enter**.

2. When it works, the line now starts with:
   ```
   postgres=#
   ```
   This means it's ready for commands.

3. Now type these **three lines one at a time**, pressing **Enter** after each.
   **Type only the lines shown — do NOT type the ``` marks.** Replace
   `StrongPass123` with a password you choose (this is your **timber password**):

   ```
   CREATE USER timber WITH PASSWORD 'StrongPass123';
   ```
   (press Enter — it replies `CREATE ROLE`)
   ```
   CREATE DATABASE timber OWNER timber;
   ```
   (press Enter — it replies `CREATE DATABASE`)
   ```
   GRANT ALL PRIVILEGES ON DATABASE timber TO timber;
   ```
   (press Enter — it replies `GRANT`)

   Keep the quote marks `'` around the password exactly as shown, and the
   semicolon `;` at the end of each line.

4. Close the black window (click the **X**). The database is created.

---

## Step 4 — Let the other PCs connect to the database

By default PostgreSQL only allows the same PC. We open it to the office network.
This means editing two small text files.

### 4a. Open the settings folder
1. Press **Windows key + R** (Run box opens).
2. Type this and press **Enter** (change **17** if you installed a different
   version number):
   ```
   C:\Program Files\PostgreSQL\17\data
   ```
   A folder opens with many files.

### 4b. Edit `postgresql.conf`
1. Press the **Windows key**, type **Notepad**, **right-click** it, choose **Run
   as administrator**, click **Yes**.
2. In Notepad: **File → Open**. Go to `C:\Program Files\PostgreSQL\17\data`.
3. At the bottom-right of the Open window, change **"Text Documents (*.txt)"** to
   **"All Files"**. Now select **`postgresql.conf`** and click **Open**.
4. Press **Ctrl+F**, type **listen_addresses**, click **Find Next**.
5. You'll see a line like `#listen_addresses = 'localhost'`. Change it to exactly:
   ```
   listen_addresses = '*'
   ```
   Make sure there is **no `#`** at the start of the line (delete it if present).
6. **File → Save**.

### 4c. Edit `pg_hba.conf`
1. Still in Notepad (as administrator): **File → Open**, "All Files", open
   **`pg_hba.conf`** from the same folder.
2. Scroll to the very bottom and add this new line (change `192.168.1.` to match
   your MAIN PC address — if your address is `192.168.0.10`, use `192.168.0.0/24`):
   ```
   host    all    all    192.168.1.0/24    scram-sha-256
   ```
3. **File → Save**. Close Notepad.

---

## Step 5 — Restart PostgreSQL so the changes take effect

1. Press the **Windows key**, type **services**, open **Services**.
2. In the list, find **postgresql-x64-17** (your version number).
3. **Right-click** it → **Restart**.

---

## Step 6 — Open the Windows Firewall for the database

1. Press the **Windows key**, type **powershell**, **right-click** **Windows
   PowerShell**, choose **Run as administrator**, click **Yes**.
2. Copy the line below, paste it into the blue window (right-click to paste), and
   press **Enter**:
   ```powershell
   New-NetFirewallRule -DisplayName "PostgreSQL LAN" -Direction Inbound -Protocol TCP -LocalPort 5432 -Action Allow -Profile Private,Domain
   ```
3. If it prints the rule details with no red error, it worked. Close the window.

---

## Step 7 — Install the app on the MAIN PC and connect it

1. Run **`AbdulSattarWoods-Setup.exe`** and finish the install. It installs for
   the current user (no admin needed) and puts a shortcut on the desktop.
   - At the end, **keep "Make the app open faster (recommended)" ticked.** It runs
     once (say **Yes** to the admin prompt) and tells Windows Defender to trust the
     app folder, so the app opens in a few seconds instead of 20-30. You can also
     run it any time later from the Start Menu ("Speed up Abdul Sattar Woods") or by
     double-clicking **`speed-up.bat`** in the install folder.
   - **Install on the PC's main drive (usually C:)**, not a secondary/USB drive —
     the app opens much faster from the main drive.
2. Open the app's install folder: press **Windows key + R**, paste this, press
   **Enter**:
   ```
   %LOCALAPPDATA%\Programs\Abdul Sattar Woods
   ```
3. Create the connection file here (see **PART 3** below for the exact "how to
   make a .env file" steps). On the MAIN PC the file contents are:
   ```
   TIMBER_DB_BACKEND=postgresql
   TIMBER_PG_HOST=127.0.0.1
   TIMBER_PG_PORT=5432
   TIMBER_PG_USER=timber
   TIMBER_PG_PASSWORD=StrongPass123
   TIMBER_PG_DB=timber
   ```
   Use the **timber password** from Step 3. On the MAIN PC the host is
   `127.0.0.1` (meaning "this same computer").
4. **Start the app.** The first time, it builds all the tables automatically and
   creates a login:
   - **Username:** `admin`
   - **Password:** `admin123`
5. Log in, then go to **Master Data → Users** and **change the admin password**,
   and add a user for each person.

> Do this MAIN PC first-run **before** setting up the other PCs.

---

# PART 2 — EACH OTHER PC (2 to 6)

On every other computer:

1. Run **`AbdulSattarWoods-Setup.exe`** and finish the install. Keep **"Make the
   app open faster (recommended)"** ticked at the end (say **Yes** to the admin
   prompt), and install on the **main drive (C:)**.
2. Open the install folder: **Windows key + R** →
   `%LOCALAPPDATA%\Programs\Abdul Sattar Woods` → **Enter**.
3. Create the same `.env` file (PART 3), but change the host to the **MAIN PC
   address** from Step 1:
   ```
   TIMBER_DB_BACKEND=postgresql
   TIMBER_PG_HOST=192.168.1.10
   TIMBER_PG_PORT=5432
   TIMBER_PG_USER=timber
   TIMBER_PG_PASSWORD=StrongPass123
   TIMBER_PG_DB=timber
   ```
   (Here `192.168.1.10` is an example — use your real MAIN PC address.)
4. Start the app. It connects to the MAIN PC and shows the same data as everyone
   else. Log in with a user account you created in Part 1.

---

# PART 3 — HOW TO CREATE THE `.env` FILE (the tricky part)

Windows can accidentally name the file `.env.txt`, which won't work. The safe way:

1. Open **Notepad** (Windows key → type Notepad → Enter).
2. Type (or paste) the six lines for this PC (from Part 1 or Part 2).
3. Click **File → Save As**.
4. In the Save window:
   - Navigate to the folder `%LOCALAPPDATA%\Programs\Abdul Sattar Woods`
     (paste that in the address bar at the top and press Enter).
   - Change **"Save as type"** at the bottom to **"All Files (*.*)"**.
   - In **File name**, type exactly:  **`.env`**
   - Click **Save**.
5. You should now see a file named just **`.env`** (no `.txt`) in that folder.

To edit it later: right-click `.env` → **Open with → Notepad**.

---

# PART 4 — CREATE THE USER ACCOUNTS

1. Log in as **admin** on any PC.
2. Go to **Master Data → Users**.
3. **Add** one account per person and give each a role:

| Person            | Role         | Can do                                             |
|-------------------|--------------|----------------------------------------------------|
| You (owner)       | **Admin**    | Everything: users, settings, delete, backups       |
| Manager           | **Manager**  | Trades, payments, edit trades, all ledgers/reports |
| Data entry staff  | **Data Entry** | Add trades & payments, view dashboard            |
| Accountant        | **Accountant** | Payments + all ledgers/reports/export            |
| View-only         | **Viewer**   | Read-only                                          |

Never share one login — the audit log tracks who did what, per account.

---

# PART 5 — BACKUPS (do on the MAIN PC only)

The data lives only on the MAIN PC, so back it up there.

1. On the MAIN PC install **Google Drive for Desktop**
   (https://www.google.com/drive/download/) and sign in. It adds a drive like
   **`G:`**.
2. Make a folder inside it, e.g. **`G:\My Drive\ASW-Backups`**.
3. In the app on the MAIN PC: **Settings → Backup folder → Change…** and pick
   that folder.
4. Turn on the automatic options in Settings:
   - **Auto-backup on exit** (backs up when the app closes)
   - **Auto-backup every** 6 h
   - **Keep backups for** 30 days
   The **Last backup** line shows when it last ran.
5. Every backup is written to that folder and Google uploads it to the cloud
   automatically. To recover: **Settings → Restore**, pick a backup, restart.

(The other PCs do not need to back up — they share the same database.)

---

# PART 6 — CHECK IT WORKS / IF SOMETHING IS WRONG

**Quick network test from another PC:**
1. On that PC: Windows key → type **powershell** → **Enter**.
2. Type (use your MAIN PC address):
   ```
   Test-NetConnection 192.168.1.10 -Port 5432
   ```
3. Look for **`TcpTestSucceeded : True`** — that means the PC can reach the
   database. Then open the app.

**Common problems:**

| What you see | Fix |
|---|---|
| App can't connect / "connection refused" | MAIN PC is off, or firewall (Step 6), or you missed `listen_addresses = '*'` / didn't restart PostgreSQL (Steps 4–5). |
| "no pg_hba.conf entry for host…" | The subnet line in `pg_hba.conf` (Step 4c) is missing or wrong. Fix it and restart PostgreSQL. |
| "password authentication failed" | The password in `.env` doesn't match the **timber password** from Step 3. |
| Works on MAIN PC but not others | Wrong `TIMBER_PG_HOST` in the client `.env`, or the address changed — recheck with `ipconfig` on the MAIN PC. |
| Password not showing while typing in SQL Shell | That's normal — it's hidden. Just type it and press Enter. |

---

# CHECKLIST

- [ ] MAIN PC address noted and fixed (Step 1)
- [ ] PostgreSQL installed; postgres password saved (Step 2)
- [ ] `timber` database + user created; timber password saved (Step 3)
- [ ] `postgresql.conf` + `pg_hba.conf` edited (Step 4)
- [ ] PostgreSQL service restarted (Step 5)
- [ ] Firewall port 5432 opened (Step 6)
- [ ] App installed on MAIN PC; `.env` uses `127.0.0.1`; first run done (Step 7)
- [ ] Admin password changed; users created (Part 4)
- [ ] App installed on each other PC; `.env` uses MAIN PC address (Part 2)
- [ ] Google Drive backup folder + auto-backup on (Part 5)
