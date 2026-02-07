"""
Email tools for Neo MCP — async IMAP/SMTP via aioimaplib + aiosmtplib.

Tools:
  - email_list: List recent emails from inbox
  - email_read: Read a specific email by UID
  - email_send: Send an email

Credentials from ~/.accounts line 1: email:app_password
"""

import os
import asyncio
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import logging

logger = logging.getLogger("neo-mcp.email")

# Gmail IMAP/SMTP settings
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def load_credentials() -> tuple[str, str]:
    """Load email:password from ~/.accounts line 1."""
    accounts_path = os.path.expanduser("~/.accounts")
    with open(accounts_path, "r") as f:
        line = f.readline().strip()
    email_addr, password = line.split(":", 1)
    return email_addr, password


def decode_mime_header(header: str) -> str:
    """Decode MIME encoded header to string."""
    if not header:
        return ""
    decoded_parts = decode_header(header)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def get_email_body(msg: email.message.Message) -> str:
    """Extract text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        # Fallback to HTML if no plain text
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return f"[HTML]\n{payload.decode(charset, errors='replace')}"
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


async def email_list_impl(n: int = 10, folder: str = "INBOX", unread_only: bool = False) -> dict:
    """List recent emails from specified folder."""
    import aioimaplib

    email_addr, password = load_credentials()

    client = aioimaplib.IMAP4_SSL(host=IMAP_HOST, port=IMAP_PORT)
    await client.wait_hello_from_server()

    await client.login(email_addr, password)
    await client.select(folder)

    # Search for emails - UNSEEN for unread, ALL for everything
    search_criteria = "UNSEEN" if unread_only else "ALL"
    status, data = await client.search(search_criteria)
    if status != "OK":
        await client.logout()
        return {"error": f"search failed: {status}"}

    # aioimaplib returns [b'1 2 3 ...', b'SEARCH completed']
    uid_line = data[0] if data else b""
    if isinstance(uid_line, bytes):
        uid_line = uid_line.decode()
    all_uids = uid_line.split()
    recent_uids = all_uids[-n:] if len(all_uids) > n else all_uids
    recent_uids = list(reversed(recent_uids))  # newest first

    emails = []
    for uid in recent_uids:
        uid_str = uid if isinstance(uid, str) else str(uid)
        status, msg_data = await client.fetch(uid_str, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        if status == "OK" and msg_data and len(msg_data) >= 2:
            # aioimaplib returns: [b'13 FETCH ...', bytearray(header), b')', b'Success']
            header_data = msg_data[1]
            if isinstance(header_data, (bytes, bytearray)):
                msg = email.message_from_bytes(bytes(header_data))
                emails.append({
                    "uid": uid_str,
                    "from": decode_mime_header(msg.get("From", "")),
                    "subject": decode_mime_header(msg.get("Subject", "")),
                    "date": msg.get("Date", ""),
                })

    await client.logout()
    return {"folder": folder, "count": len(emails), "emails": emails}


async def email_read_impl(uid: str, folder: str = "INBOX") -> dict:
    """Read a specific email by UID."""
    import aioimaplib
    import aiohttp

    email_addr, password = load_credentials()

    client = aioimaplib.IMAP4_SSL(host=IMAP_HOST, port=IMAP_PORT)
    await client.wait_hello_from_server()

    await client.login(email_addr, password)
    await client.select(folder)

    status, msg_data = await client.fetch(uid, "(RFC822)")
    if status != "OK":
        await client.logout()
        return {"error": f"fetch failed: {status}"}

    result = {"uid": uid, "error": "could not parse email"}

    # aioimaplib returns: [b'13 FETCH ...', bytearray(email), b')', b'Success']
    if len(msg_data) >= 2:
        raw_email = msg_data[1]
        if isinstance(raw_email, (bytes, bytearray)):
            msg = email.message_from_bytes(bytes(raw_email))
            result = {
                "uid": uid,
                "from": decode_mime_header(msg.get("From", "")),
                "to": decode_mime_header(msg.get("To", "")),
                "subject": decode_mime_header(msg.get("Subject", "")),
                "date": msg.get("Date", ""),
                "body": get_email_body(msg)[:4000],  # truncate for context
            }
            # Mark as read
            await client.store(uid, "+FLAGS", "(\\Seen)")

            # Notify neo-console to refresh unread count
            try:
                async with aiohttp.ClientSession() as session:
                    await session.post("http://localhost:5000/email/refresh", timeout=aiohttp.ClientTimeout(total=2))
            except Exception:
                pass  # Best effort — don't fail if neo-console unreachable

    await client.logout()
    return result


async def email_send_impl(to: str, subject: str, body: str, html: bool = False) -> dict:
    """Send an email."""
    import aiosmtplib

    email_addr, password = load_credentials()

    if html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "html"))
    else:
        msg = MIMEText(body)

    msg["From"] = email_addr
    msg["To"] = to
    msg["Subject"] = subject

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=email_addr,
            password=password,
            start_tls=True,
        )
        return {"status": "sent", "to": to, "subject": subject}
    except Exception as e:
        logger.exception("send failed")
        return {"status": "error", "error": str(e)}


# Sync wrappers for MCP tools — run in separate thread to avoid nested event loop issues
import concurrent.futures

def _run_async(coro):
    """Run async coroutine in a new event loop in a separate thread."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result(timeout=30)


def email_list(n: int = 10, folder: str = "INBOX", unread_only: bool = False) -> dict:
    """List recent emails."""
    return _run_async(email_list_impl(n, folder, unread_only))


def email_read(uid: str, folder: str = "INBOX") -> dict:
    """Read email by UID."""
    return _run_async(email_read_impl(uid, folder))


def email_send(to: str, subject: str, body: str, html: bool = False) -> dict:
    """Send email."""
    return _run_async(email_send_impl(to, subject, body, html))
