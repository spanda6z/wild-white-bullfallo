import asyncio, logging, os, random, re, time
from collections import defaultdict, deque
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ChatJoinRequestHandler, ChatMemberHandler, ContextTypes, filters

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("wild-white-bullffalo")
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GROUP_ID = int(os.environ["TELEGRAM_GROUP_ID"])
MINT = os.getenv("SOLANA_TOKEN_MINT", "5T7V8epXn2LeoyxqzkWa1pPStJGGQ2i3cQiUQvw8pump")
HELIUS_KEY = os.getenv("HELIUS_API_KEY", "")
VERIFY_TTL = int(os.getenv("VERIFY_TTL_SECONDS", "180"))
RAID_THRESHOLD = int(os.getenv("RAID_THRESHOLD", "12"))
RAID_WINDOW = int(os.getenv("RAID_WINDOW_SECONDS", "30"))
FLOOD_MAX = int(os.getenv("FLOOD_MAX_MESSAGES", "6"))
FLOOD_WINDOW = int(os.getenv("FLOOD_WINDOW_SECONDS", "8"))
admins = {int(x) for x in os.getenv("ADMIN_USER_IDS", "").split(",") if x.strip().isdigit()}
pending, seen = {}, set()
joins = deque()
messages = defaultdict(deque)
raid_until = 0
restricted = ChatPermissions(can_send_messages=False, can_send_audios=False, can_send_documents=False, can_send_photos=False, can_send_videos=False, can_send_video_notes=False, can_send_voice_notes=False, can_send_polls=False, can_send_other_messages=False, can_add_web_page_previews=False)
unrestricted = ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True)

def is_admin(update):
    return bool(update.effective_user and update.effective_user.id in admins)

async def notice(app, text):
    try: await app.bot.send_message(GROUP_ID, "🛡️ <b>WILD WHITE BULLFFALO</b>\n" + text, parse_mode=ParseMode.HTML)
    except Exception: log.exception("Admin notice failed")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("🐃 WILD WHITE BULLFFALO — anti-raid, human verification, and Solana buy alerts.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    await update.effective_message.reply_text(f"Pending: {len(pending)}\nRaid mode: {'ACTIVE' if time.time() < raid_until else 'off'}\nHelius alerts: {'configured' if HELIUS_KEY else 'NOT CONFIGURED'}\nMint: {MINT}")

async def lockdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global raid_until
    if is_admin(update):
        raid_until = time.time() + 900
        await update.effective_message.reply_text("🔒 Raid lockdown active for 15 minutes.")

async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global raid_until
    if is_admin(update):
        raid_until = 0
        await update.effective_message.reply_text("🔓 Manual raid lockdown ended.")

async def verifycheck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update): await update.effective_message.reply_text(f"Pending verifications: {len(pending)}")

async def challenge(app, user):
    a, b = random.randint(2, 9), random.randint(2, 9)
    answer = a + b
    nonce = f"{user.id}:{int(time.time())}:{random.randint(10000,99999)}"
    pending[user.id] = {"answer": answer, "expires": time.time() + VERIFY_TTL, "nonce": nonce, "attempts": 0}
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ I'm human — start check", callback_data=f"begin:{user.id}:{nonce}")]])
    await app.bot.send_message(GROUP_ID, f"🐃 Welcome {user.mention_html()}! You are muted until you tap the button and solve a short math question within {VERIFY_TTL} seconds.", parse_mode=ParseMode.HTML, reply_markup=keyboard)

async def joined(app, user):
    global raid_until
    now = time.time()
    joins.append(now)
    while joins and now - joins[0] > RAID_WINDOW: joins.popleft()
    await app.bot.restrict_chat_member(GROUP_ID, user.id, restricted)
    if len(joins) >= RAID_THRESHOLD:
        raid_until = max(raid_until, now + 900)
        await notice(app, f"🚨 Possible raid: {len(joins)} joins in {RAID_WINDOW} seconds. New members are restricted pending verification.")
    await challenge(app, user)

async def join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    if req.chat.id != GROUP_ID: return
    # Approve into a muted state so the verification buttons can be shown in the group.
    try:
        await req.approve()
        await joined(context.application, req.from_user)
    except Exception: log.exception("Join request processing failed")

async def member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cm = update.chat_member
    if not cm or cm.chat.id != GROUP_ID: return
    old, new = cm.old_chat_member, cm.new_chat_member
    if old.status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED) and new.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED):
        if new.user.is_bot:
            try: await context.bot.ban_chat_member(GROUP_ID, new.user.id)
            except Exception: log.exception("Could not remove bot account")
            return
        try: await joined(context.application, new.user)
        except Exception: log.exception("Join handling failed")

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = (q.data or "").split(":")
    if len(parts) < 2 or not parts[1].isdigit(): return
    uid = int(parts[1])
    if q.from_user.id != uid and q.from_user.id not in admins:
        await q.answer("This verification belongs to another member.", show_alert=True); return
    record = pending.get(uid)
    if not record or record["expires"] < time.time():
        pending.pop(uid, None)
        await q.edit_message_text("⌛ Verification expired. Please ask an admin for a new challenge."); return
    if parts[0] == "begin":
        if len(parts) != 3 or parts[2] != record["nonce"]: return
        a, b = random.randint(2, 9), random.randint(2, 9)
        record["answer"] = a + b
        choices = {a+b, max(0, a+b+random.choice([-3,-2,2,3]))}
        while len(choices) < 3: choices.add(random.randint(2, 20))
        buttons = [[InlineKeyboardButton(str(n), callback_data=f"answer:{uid}:{n}:{record['nonce']}")] for n in random.sample(list(choices), len(choices))]
        await q.edit_message_text(f"🧠 Human check: what is <b>{a} + {b}</b>?", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))
    elif parts[0] == "answer":
        if len(parts) != 4 or parts[3] != record["nonce"]: return
        if not parts[2].isdigit() or int(parts[2]) != record["answer"]:
            record["attempts"] += 1
            if record["attempts"] >= 3:
                pending.pop(uid, None)
                try: await context.bot.ban_chat_member(GROUP_ID, uid); await q.edit_message_text("❌ Verification failed; account removed.")
                except Exception: await q.edit_message_text("❌ Verification failed. Contact an admin.")
            else: await q.answer(f"Incorrect. Attempts remaining: {3-record['attempts']}", show_alert=True)
            return
        try:
            await context.bot.restrict_chat_member(GROUP_ID, uid, unrestricted)
            pending.pop(uid, None)
            await q.edit_message_text("✅ Verified! Welcome to WILD WHITE BULLFFALO.")
        except Exception:
            log.exception("Failed to restore member permissions")
            await q.edit_message_text("Verification passed, but permissions could not be changed. Contact an admin.")

URL = re.compile(r"(https?://|t\.me/|www\.|discord\.gg/)", re.I)
async def moderate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, user = update.effective_message, update.effective_user
    if not msg or not user or msg.chat.id != GROUP_ID or user.is_bot: return
    try:
        member = await context.bot.get_chat_member(GROUP_ID, user.id)
        if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER): return
    except Exception: pass
    now = time.time(); bucket = messages[user.id]; bucket.append(now)
    while bucket and now - bucket[0] > FLOOD_WINDOW: bucket.popleft()
    text = msg.text or msg.caption or ""
    reason = "message flood" if len(bucket) > FLOOD_MAX else ("unapproved link" if URL.search(text) and os.getenv("ALLOW_MEMBER_LINKS", "false").lower() != "true" else None)
    if reason:
        try: await msg.delete()
        except Exception: pass
        try: await context.bot.restrict_chat_member(GROUP_ID, user.id, restricted, until_date=int(now+300))
        except Exception: pass
        await notice(context.application, f"⚠️ Filter action: {reason}; user <code>{user.id}</code> muted for 5 minutes.")

async def solana_watcher(app):
    if not HELIUS_KEY:
        log.warning("HELIUS_API_KEY missing; buy alerts disabled."); return
    url = f"https://api.helius.xyz/v0/addresses/{MINT}/transactions?api-key={HELIUS_KEY}&limit=50"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        while True:
            try:
                async with session.get(url) as r:
                    if r.status != 200:
                        log.warning("Helius HTTP %s", r.status); await asyncio.sleep(10); continue
                    txs = await r.json()
                for tx in reversed(txs if isinstance(txs, list) else []):
                    sig = tx.get("signature")
                    if not sig or sig in seen: continue
                    seen.add(sig)
                    if len(seen) > 10000: seen.clear(); seen.add(sig)
                    if (tx.get("type") or "").upper() != "SWAP": continue
                    transfers = [t for t in tx.get("tokenTransfers", []) if t.get("mint") == MINT and float(t.get("tokenAmount") or 0) > 0]
                    if not transfers: continue
                    amount = sum(float(t.get("tokenAmount") or 0) for t in transfers)
                    buyer = transfers[0].get("toUserAccount") or tx.get("feePayer") or "Unknown"
                    sig_url = "https://solscan.io/tx/" + sig
                    chart_url = "https://dexscreener.com/solana/" + MINT
                    buy_url = "https://pump.fun/coin/" + MINT
                    short_buyer = buyer if len(buyer) <= 12 else buyer[:5] + "..." + buyer[-4:]
                    text = ("🟠 <b>NEW BUY · WILD WHITE BULLFFALO</b>\\n"
                            "━━━━━━━━━━━━━━━━━━\\n"
                            "🐃 <b>$BULLFFALO BUY</b> · <i>Solana</i>\\n\\n"
                            f"🪙 <b>{amount:,.2f}</b> tokens\\n"
                            f"👛 <code>{short_buyer}</code> · <a href=\\\"{sig_url}\\\">Tx</a>\\n"
                            "🟢 <b>BUY DETECTED</b>\\n"
                            "━━━━━━━━━━━━━━━━━━\\n"
                            "<i>On-chain swap alert · amounts are token units</i>")
                    keyboard = InlineKeyboardMarkup([[
                        InlineKeyboardButton("📊 Chart", url=chart_url),
                        InlineKeyboardButton("🟠 Buy", url=buy_url),
                        InlineKeyboardButton("🔎 Transaction", url=sig_url)
                    ]])
                    await app.bot.send_message(GROUP_ID, text, parse_mode=ParseMode.HTML,
                                               reply_markup=keyboard, disable_web_page_preview=True)
                await asyncio.sleep(5)
            except asyncio.CancelledError: raise
            except Exception: log.exception("Helius poll failed"); await asyncio.sleep(10)

async def post_init(app):
    app.create_task(solana_watcher(app))
    async def expire():
        while True:
            now = time.time()
            for uid, data in list(pending.items()):
                if data["expires"] < now:
                    pending.pop(uid, None)
                    try:
                        await app.bot.ban_chat_member(GROUP_ID, uid)
                        await notice(app, f"⌛ Removed unverified member <code>{uid}</code> after timeout.")
                    except Exception: log.exception("Could not remove expired member")
            await asyncio.sleep(10)
    app.create_task(expire())

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("lockdown", lockdown))
    app.add_handler(CommandHandler("unlock", unlock))
    app.add_handler(CommandHandler("verifycheck", verifycheck))
    app.add_handler(ChatJoinRequestHandler(join_request))
    app.add_handler(ChatMemberHandler(member_update, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.Chat(GROUP_ID) & ~filters.StatusUpdate.ALL, moderate))
    log.info("Starting WILD WHITE BULLFFALO")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__": main()
