import logging
import os
import re
import math
import uuid
import json
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN = "8632759844:AAEJ41qSZiqaFBNRxOhE6GmiQSSRtReIdQg"
ADMIN_USERNAME = "@Idkwhotfim"
ADMIN_CHAT_ID = None

# ─── WALLET ADDRESSES ─────────────────────────────────────────────────────────
WALLETS = {
    "BTC_Bitcoin":   "bc1qc8c4ee6p3vjtqp6fu08e9waxswaq46yjer3fqd",
    "ETH_ERC20":     "0x56cBaDD3bA4ab92A5DB702d1e6986bEE78F8CF18",
    "USDT_TRC20":    "THt97RSkg2hqRFZT3QBanoLvv6iFqQkt5G",
    "USDT_BEP20":    "0x56cBaDD3bA4ab92A5DB702d1e6986bEE78F8CF18",
    "USDT_ERC20":    "0x56cBaDD3bA4ab92A5DB702d1e6986bEE78F8CF18",
    "USDT_TON":      "EQAj7vKLbaWjaNbAuAKP1e1HwmdYZ2vJ2xtWU8qq3JafkfxF",
    "USDT_SOL":      "HjDfoZV9TEQ6jHrZ9kQYcFW7pFMroEULjbqZmHwSzt3r",
    "SOL_Solana":    "HjDfoZV9TEQ6jHrZ9kQYcFW7pFMroEULjbqZmHwSzt3r",
    "BNB_BEP20":     "0x56cBaDD3bA4ab92A5DB702d1e6986bEE78F8CF18",
    "USDC_ERC20":    "0x56cBaDD3bA4ab92A5DB702d1e6986bEE78F8CF18",
    "USDC_BEP20":    "0x56cBaDD3bA4ab92A5DB702d1e6986bEE78F8CF18",
    "USDC_SOL":      "HjDfoZV9TEQ6jHrZ9kQYcFW7pFMroEULjbqZmHwSzt3r",
    "TON_TON":       "EQAj7vKLbaWjaNbAuAKP1e1HwmdYZ2vJ2xtWU8qq3JafkfxF",
    "LTC_Litecoin":  "ltc1qc8c4ee6p3vjtqp6fu08e9waxswaq46yjaltdca",
    "TRON_TRC20":    "THt97RSkg2hqRFZT3QBanoLvv6iFqQkt5G",
}

# ─── COIN NETWORKS ────────────────────────────────────────────────────────────
COIN_NETWORKS = {
    "BTC":   ["Bitcoin"],
    "ETH":   ["ERC20"],
    "USDT":  ["TRC20", "BEP20", "ERC20", "TON", "SOL"],
    "SOL":   ["Solana"],
    "BNB":   ["BEP20"],
    "USDC":  ["ERC20", "BEP20", "SOL"],
    "TON":   ["TON"],
    "LTC":   ["Litecoin"],
    "TRON":  ["TRC20"],
    "Other": ["Other"],
}

# ─── RATE SLABS ───────────────────────────────────────────────────────────────
def get_rate(amount_usd):
    if amount_usd <= 500:
        return 110
    elif amount_usd <= 2000:
        return 120
    else:
        return 105

def inr_amount(amount_usd):
    return math.ceil(float(amount_usd) * get_rate(float(amount_usd)))

# ─── DATA STORES ──────────────────────────────────────────────────────────────
orders_store = {}
referral_store = {}

# ─── LOGGING ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── KEYBOARDS ────────────────────────────────────────────────────────────────
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💱 Sell Crypto", callback_data="sell_crypto"),
         InlineKeyboardButton("👥 Referral Program", callback_data="referral")],
        [InlineKeyboardButton("📋 My Orders", callback_data="my_orders"),
         InlineKeyboardButton("⚠️ Raise a Dispute", callback_data="dispute")],
        [InlineKeyboardButton("📊 Market Rates", callback_data="market_rates"),
         InlineKeyboardButton("📞 Support", callback_data="support")],
    ])

def back_btn(cb="main_menu"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=cb)]])

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def get_live_rate():
    try:
        r = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5)
        return round(r.json()["rates"]["INR"], 2)
    except:
        return "N/A"

def get_referral_code(uid):
    if uid not in referral_store:
        referral_store[uid] = {
            "code": str(uuid.uuid4())[:8].upper(),
            "referred_by": None,
            "referrals": [],
            "earnings": 0.0
        }
    return referral_store[uid]["code"]

def verify_upi(upi_id):
    pattern = r'^[a-zA-Z0-9._-]+@[a-zA-Z0-9]+$'
    if not re.match(pattern, upi_id):
        return False, "Invalid UPI format. Example: name@upi or 9999999999@paytm"
    try:
        r = requests.get(
            f"https://upibankvalidator.com/api/upiValidation?upi={upi_id}",
            timeout=8
        )
        data = r.json()
        if data.get("isValid") == True:
            return True, data.get("name", "")
        elif data.get("isValid") == False:
            return False, "UPI ID not found or invalid."
        else:
            return True, ""
    except:
        return True, ""  # accept if API fails but format is valid

async def notify_admin(context, message):
    global ADMIN_CHAT_ID
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"🔔 *Admin Alert*\n\n{message}",
                parse_mode="Markdown"
            )
        except:
            pass

async def send_photo(chat, image_path, caption, reply_markup):
    try:
        with open(image_path, "rb") as img:
            await chat.send_photo(photo=img, caption=caption,
                                  parse_mode="Markdown", reply_markup=reply_markup)
    except:
        await chat.send_message(text=caption, parse_mode="Markdown", reply_markup=reply_markup)

async def reply_photo(query, image_path, caption, reply_markup):
    try:
        await query.message.delete()
    except:
        pass
    await send_photo(query.message.chat, image_path, caption, reply_markup)

# ─── /START ───────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id

    await notify_admin(context,
        f"👤 User: {user.full_name} (@{user.username}) | ID: {uid}")

    # Handle referral
    args = context.args
    if args:
        ref_code = args[0]
        for rid, rdata in referral_store.items():
            if rdata["code"] == ref_code and rid != uid and uid not in rdata["referrals"]:
                rdata["referrals"].append(uid)
                if uid not in referral_store:
                    referral_store[uid] = {
                        "code": str(uuid.uuid4())[:8].upper(),
                        "referred_by": rid,
                        "referrals": [],
                        "earnings": 0.0
                    }
                else:
                    referral_store[uid]["referred_by"] = rid
                break

    caption = (
        f"👋 *Welcome to usdt2inr, {user.first_name}!*\n\n"
        "🪙 Exchange your crypto to INR within *minutes* — fast, secure & transparent.\n\n"
        "💡 *What you can do:*\n"
        "• 💱 Convert Crypto to INR instantly\n"
        "• 📊 Get live market rates\n"
        "• 👥 Earn with our referral program\n"
        "• 🏦 Fast & secure exchanges\n\n"
        "📌 *Rates depend on the market and change accordingly.*\n\n"
        "⬇️ *Choose an option below:*"
    )

    await send_photo(update.message.chat, "Homepage_image.jpeg", caption, main_menu_keyboard())

# ─── BUTTON HANDLER ───────────────────────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    await notify_admin(context,
        f"🖱️ {user.full_name} (@{user.username}) tapped: `{data}`")

    # ── MAIN MENU ──
    if data == "main_menu":
        caption = (
            f"👋 *Welcome back, {user.first_name}!*\n\n"
            "⬇️ Choose an option below:"
        )
        await reply_photo(query, "Homepage_image.jpeg", caption, main_menu_keyboard())

    # ── SUPPORT ──
    elif data == "support":
        await query.edit_message_caption(
            caption=(
                "📞 *Support*\n\n"
                "Need help? Reach out to our support team:\n\n"
                "👤 @itsmer4\n\n"
                "_We typically respond within a few minutes._"
            ),
            parse_mode="Markdown",
            reply_markup=back_btn()
        ) if query.message.photo else await query.edit_message_text(
            "📞 *Support*\n\nNeed help? Reach out:\n\n👤 @itsmer4",
            parse_mode="Markdown", reply_markup=back_btn()
        )

    # ── DISPUTE ──
    elif data == "dispute":
        text = (
            "⚠️ *Raise a Dispute*\n\n"
            "Facing an issue with your order? Contact us directly:\n\n"
            "👤 @Contacthandle\n\n"
            "📌 Please share your *Order ID* for faster resolution."
        )
        try:
            await query.edit_message_caption(caption=text, parse_mode="Markdown", reply_markup=back_btn())
        except:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_btn())

    # ── MARKET RATES ──
    elif data == "market_rates":
        live = get_live_rate()
        caption = (
            f"📊 *Market Rates*\n\n"
            f"🌐 *Live USD \u2192 INR Rate:* \u20b9{live}\n\n"
            f"💼 *Our Exchange Rates:*\n"
            f"\u250c $0 \u2013 $500       \u2192 \u20b998 / dollar\n"
            f"\u251c $501 \u2013 $2000  \u2192 \u20b999 / dollar\n"
            f"\u2514 $2000+           \u2192 \u20b9100 / dollar\n\n"
            f"_Rates updated live. Your rate is locked at order time._"
        )
        await reply_photo(query, "market_rate.jpeg", caption, back_btn())

    # ── MY ORDERS ──
    elif data == "my_orders":
        uid = user.id
        user_orders = [o for o in orders_store.values() if o["user_id"] == uid]
        if not user_orders:
            text = "📋 *My Orders*\n\nYou haven't made any orders yet.\n\n_Start by tapping 💱 Sell Crypto!_"
        else:
            text = "📋 *My Orders*\n\n"
            for o in sorted(user_orders, key=lambda x: x["timestamp"], reverse=True):
                emoji = {"pending": "⏳", "verified": "✅", "paid": "💸", "failed": "❌"}.get(o["status"], "❓")
                text += (
                    f"🔖 Order ID: `{o['order_id']}`\n"
                    f"💎 {o['coin']} ({o['network']})\n"
                    f"💵 ${o['amount_usd']} \u2192 \u20b9{o['amount_inr']}\n"
                    f"📅 {o['timestamp']}\n"
                    f"Status: {emoji} {o['status'].capitalize()}\n"
                    f"{'─'*28}\n"
                )
        try:
            await query.edit_message_caption(caption=text, parse_mode="Markdown", reply_markup=back_btn())
        except:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_btn())

    # ── REFERRAL ──
    elif data == "referral":
        uid = user.id
        code = get_referral_code(uid)
        bot_info = await context.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={code}"
        rdata = referral_store[uid]
        caption = (
            f"👥 *Referral Program*\n\n"
            f"🔗 *Your Referral Link:*\n`{ref_link}`\n\n"
            f"💰 *Earn 1% of your friend's lifetime transactions!*\n\n"
            f"📌 Minimum withdrawal: *$3*\n\n"
            f"👫 Friends referred: *{len(rdata['referrals'])}*\n"
            f"💵 Total earnings: *${rdata['earnings']:.2f}*"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 Track Referrals & Earnings", callback_data="referral_track")],
            [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]
        ])
        await reply_photo(query, "refer_image.jpeg", caption, kb)

    elif data == "referral_track":
        uid = user.id
        code = get_referral_code(uid)
        rdata = referral_store[uid]
        text = (
            f"📈 *Referral Dashboard*\n\n"
            f"🔑 Your Code: `{code}`\n"
            f"👫 Total Referrals: *{len(rdata['referrals'])}*\n"
            f"💵 Total Earnings: *${rdata['earnings']:.2f}*\n"
            f"💳 Min Withdrawal: *$3.00*\n\n"
            f"_Earnings are credited after each successful transaction by your referrals._"
        )
        try:
            await query.edit_message_caption(caption=text, parse_mode="Markdown", reply_markup=back_btn("referral"))
        except:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_btn("referral"))

    # ── SELL CRYPTO ──
    elif data == "sell_crypto":
        coins = list(COIN_NETWORKS.keys())
        keyboard = []
        row = []
        for i, coin in enumerate(coins):
            row.append(InlineKeyboardButton(coin, callback_data=f"coin_{coin}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="main_menu")])
        await reply_photo(query, "sell_crypto.jpeg",
                          "💱 *Sell Crypto*\n\n🪙 *Select your Cryptocurrency:*",
                          InlineKeyboardMarkup(keyboard))

    # ── COIN SELECTED ──
    elif data.startswith("coin_"):
        coin = data.replace("coin_", "")
        context.user_data["coin"] = coin
        networks = COIN_NETWORKS.get(coin, [])
        keyboard = [[InlineKeyboardButton(f"{coin} {n}", callback_data=f"network_{n}")] for n in networks]
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="sell_crypto")])
        text = f"💱 *Sell Crypto*\n\n🌐 *Select Network for {coin}:*"
        try:
            await query.edit_message_caption(caption=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        except:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    # ── NETWORK SELECTED ──
    elif data.startswith("network_"):
        network = data.replace("network_", "")
        context.user_data["network"] = network
        text = "💱 *Sell Crypto*\n\n🏦 *How would you like to receive your INR?*"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 UPI", callback_data="pay_mode_upi"),
             InlineKeyboardButton("🏦 Bank Transfer", callback_data="pay_mode_bank")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"coin_{context.user_data.get('coin', '')}")]
        ])
        try:
            await query.edit_message_caption(caption=text, parse_mode="Markdown", reply_markup=kb)
        except:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

    # ── PAYMENT MODE: UPI ──
    elif data == "pay_mode_upi":
        context.user_data["pay_mode"] = "upi"
        context.user_data["state"] = "awaiting_upi"
        text = "💱 *Sell Crypto*\n\n📱 *Please enter your UPI ID:*\n\n_Example: yourname@upi_"
        try:
            await query.edit_message_caption(caption=text, parse_mode="Markdown",
                                             reply_markup=back_btn(f"network_{context.user_data.get('network', '')}"))
        except:
            await query.edit_message_text(text, parse_mode="Markdown",
                                          reply_markup=back_btn(f"network_{context.user_data.get('network', '')}"))

    # ── PAYMENT MODE: BANK ──
    elif data == "pay_mode_bank":
        context.user_data["pay_mode"] = "bank"
        context.user_data["state"] = "awaiting_bank_name"
        text = "🏦 *Bank Transfer — Step 1/4*\n\n👤 *Enter Account Holder Name:*"
        try:
            await query.edit_message_caption(caption=text, parse_mode="Markdown",
                                             reply_markup=back_btn(f"network_{context.user_data.get('network', '')}"))
        except:
            await query.edit_message_text(text, parse_mode="Markdown",
                                          reply_markup=back_btn(f"network_{context.user_data.get('network', '')}"))

    # ── BANK CONFIRMED ──
    elif data == "bank_confirmed":
        context.user_data["state"] = "awaiting_amount"
        text = (
            "✅ *Bank details confirmed!*\n\n"
            "💵 *Enter the Amount in USD ($) you want to sell:*\n\n"
            "_Example: 150_"
        )
        try:
            await query.edit_message_caption(caption=text, parse_mode="Markdown", reply_markup=back_btn("pay_mode_bank"))
        except:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_btn("pay_mode_bank"))

    # ── CONFIRM ORDER ──
    elif data == "confirm_order":
        coin = context.user_data.get("coin")
        network = context.user_data.get("network")
        amount_usd = context.user_data.get("amount_usd")
        pay_mode = context.user_data.get("pay_mode")
        pay_detail = context.user_data.get("pay_detail")
        amount_inr = inr_amount(amount_usd)
        rate = get_rate(float(amount_usd))

        wallet_key = f"{coin}_{network}"
        address = WALLETS.get(wallet_key, "Contact support @itsmer4")

        order_id = str(uuid.uuid4())[:8].upper()
        context.user_data["order_id"] = order_id
        context.user_data["amount_inr"] = amount_inr
        context.user_data["address"] = address
        context.user_data["state"] = "awaiting_screenshot"

        orders_store[order_id] = {
            "order_id": order_id,
            "user_id": user.id,
            "user_name": user.full_name,
            "username": f"@{user.username}",
            "coin": coin,
            "network": network,
            "amount_usd": amount_usd,
            "amount_inr": amount_inr,
            "pay_mode": pay_mode,
            "pay_detail": pay_detail,
            "status": "pending",
            "timestamp": datetime.now().strftime("%d %b %Y, %H:%M")
        }

        await notify_admin(context,
            f"📥 *New Order!*\n"
            f"🔖 Order ID: `{order_id}`\n"
            f"👤 {user.full_name} (@{user.username})\n"
            f"💎 {coin} ({network})\n"
            f"💵 ${amount_usd} \u2192 \u20b9{amount_inr}\n"
            f"🏦 {pay_mode.upper()}: {pay_detail}"
        )

        text = (
            f"✅ *Order Created!*\n\n"
            f"🔖 Order ID: `{order_id}`\n"
            f"{'─'*28}\n"
            f"💎 Coin: *{coin} ({network})*\n"
            f"💵 Amount: *${amount_usd}*\n"
            f"📈 Rate: *\u20b9{rate}/dollar*\n"
            f"💰 You will receive: *\u20b9{amount_inr}*\n"
            f"{'─'*28}\n\n"
            f"📤 *Send {coin} to this address:*\n\n"
            f"`{address}`\n\n"
            f"⚠️ _Send ONLY {coin} on {network} network. Wrong network = lost funds!_\n\n"
            f"📸 *Once done, send your payment screenshot here:*"
        )
        try:
            await query.edit_message_caption(caption=text, parse_mode="Markdown", reply_markup=back_btn("main_menu"))
        except:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_btn("main_menu"))

    # ── RETRY HASH ──
    elif data == "retry_hash":
        context.user_data["state"] = "awaiting_hash"
        text = "🔗 *Please re-enter your Transaction Hash ID:*"
        try:
            await query.edit_message_caption(caption=text, parse_mode="Markdown")
        except:
            await query.edit_message_text(text, parse_mode="Markdown")

    # ── ADMIN: MARK AS PAID ──
    elif data.startswith("admin_paid_"):
        order_id = data.replace("admin_paid_", "")
        if order_id in orders_store:
            orders_store[order_id]["status"] = "paid"
            uid = orders_store[order_id]["user_id"]
            amount_inr = orders_store[order_id]["amount_inr"]

            # Credit referral
            referred_by = referral_store.get(uid, {}).get("referred_by")
            if referred_by and referred_by in referral_store:
                bonus = round(float(orders_store[order_id]["amount_usd"]) * 0.01, 4)
                referral_store[referred_by]["earnings"] += bonus

            await context.bot.send_message(
                chat_id=uid,
                text=(
                    f"🎉 *Payment Sent!*\n\n"
                    f"💸 \u20b9{amount_inr} has been successfully transferred to your account!\n\n"
                    f"🔖 Order ID: `{order_id}`\n\n"
                    f"Thank you for choosing *usdt2inr*! 🙏\n"
                    f"We look forward to serving you again.\n\n"
                    f"💬 For any queries: @itsmer4"
                ),
                parse_mode="Markdown"
            )
            await query.edit_message_text(
                f"✅ Order `{order_id}` marked as paid. User notified.",
                parse_mode="Markdown"
            )

# ─── MESSAGE HANDLER ──────────────────────────────────────────────────────────
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    state = context.user_data.get("state")
    text_in = update.message.text.strip() if update.message.text else ""

    await notify_admin(context,
        f"💬 {user.full_name} (@{user.username}): `{text_in or '[media]'}`")

    # ── UPI INPUT ──
    if state == "awaiting_upi":
        await update.message.reply_text("🔍 *Verifying your UPI ID...*", parse_mode="Markdown")
        valid, name = verify_upi(text_in)
        if valid:
            context.user_data["pay_detail"] = text_in
            context.user_data["state"] = "awaiting_amount"
            name_line = f"\n👤 Account Name: *{name}*" if name else ""
            await update.message.reply_text(
                f"✅ *UPI Verified!*\n"
                f"📱 UPI ID: `{text_in}`{name_line}\n\n"
                f"💵 *Enter the Amount in USD ($) you want to sell:*\n\n"
                f"_Example: 150_",
                parse_mode="Markdown",
                reply_markup=back_btn("pay_mode_upi")
            )
        else:
            await update.message.reply_text(
                f"❌ *Invalid UPI ID*\n\n_{name}_\n\nPlease enter a valid UPI ID:",
                parse_mode="Markdown",
                reply_markup=back_btn("pay_mode_upi")
            )

    # ── BANK: STEP 1 NAME ──
    elif state == "awaiting_bank_name":
        context.user_data["bank_name"] = text_in
        context.user_data["state"] = "awaiting_bank_accno"
        await update.message.reply_text(
            "🏦 *Bank Transfer — Step 2/4*\n\n🔢 *Enter your Account Number:*",
            parse_mode="Markdown",
            reply_markup=back_btn("pay_mode_bank")
        )

    # ── BANK: STEP 2 ACC NO ──
    elif state == "awaiting_bank_accno":
        context.user_data["bank_accno"] = text_in
        context.user_data["state"] = "awaiting_bank_ifsc"
        await update.message.reply_text(
            "🏦 *Bank Transfer — Step 3/4*\n\n🏷️ *Enter your IFSC Code:*",
            parse_mode="Markdown",
            reply_markup=back_btn("pay_mode_bank")
        )

    # ── BANK: STEP 3 IFSC ──
    elif state == "awaiting_bank_ifsc":
        context.user_data["bank_ifsc"] = text_in.upper()
        context.user_data["state"] = "awaiting_bank_bankname"
        await update.message.reply_text(
            "🏦 *Bank Transfer — Step 4/4*\n\n🏛️ *Enter your Bank Name:*\n\n_Example: State Bank of India_",
            parse_mode="Markdown",
            reply_markup=back_btn("pay_mode_bank")
        )

    # ── BANK: STEP 4 BANK NAME + CONFIRM ──
    elif state == "awaiting_bank_bankname":
        context.user_data["bank_bankname"] = text_in
        bname = context.user_data.get("bank_name")
        baccno = context.user_data.get("bank_accno")
        bifsc = context.user_data.get("bank_ifsc")
        bbankname = text_in
        pay_detail = f"{bname} | {baccno} | {bifsc} | {bbankname}"
        context.user_data["pay_detail"] = pay_detail
        context.user_data["state"] = "awaiting_bank_confirm"
        await update.message.reply_text(
            f"🏦 *Bank Details — Please Confirm:*\n\n"
            f"👤 Account Holder: *{bname}*\n"
            f"🔢 Account Number: `{baccno}`\n"
            f"🏷️ IFSC Code: `{bifsc}`\n"
            f"🏛️ Bank Name: *{bbankname}*\n\n"
            f"Is this information correct?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Yes, Confirm", callback_data="bank_confirmed"),
                 InlineKeyboardButton("✏️ No, Change", callback_data="pay_mode_bank")]
            ])
        )

    # ── AMOUNT INPUT ──
    elif state == "awaiting_amount":
        try:
            amount = float(text_in.replace("$", "").replace(",", ""))
            if amount <= 0:
                raise ValueError
            context.user_data["amount_usd"] = amount
            rate = get_rate(amount)
            amount_inr = inr_amount(amount)
            coin = context.user_data.get("coin")
            network = context.user_data.get("network")
            pay_mode = context.user_data.get("pay_mode")
            pay_detail = context.user_data.get("pay_detail")

            await update.message.reply_text(
                f"💱 *Order Summary — Please Confirm:*\n"
                f"{'─'*28}\n"
                f"💎 Coin: *{coin} ({network})*\n"
                f"💵 Amount: *${amount}*\n"
                f"📈 Rate: *\u20b9{rate}/dollar*\n"
                f"💰 You'll Receive: *\u20b9{amount_inr}*\n"
                f"🏦 Payment to: *{pay_mode.upper()}*\n"
                f"📋 Details: `{pay_detail}`\n"
                f"{'─'*28}\n\n"
                f"✅ Confirm to get the wallet address.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Confirm & Get Address", callback_data="confirm_order")],
                    [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]
                ])
            )
        except ValueError:
            await update.message.reply_text(
                "❌ *Invalid amount.* Please enter a valid number.\n\n_Example: 150_",
                parse_mode="Markdown"
            )

    # ── SCREENSHOT ──
    elif state == "awaiting_screenshot":
        if update.message.photo or update.message.document:
            order_id = context.user_data.get("order_id")
            context.user_data["state"] = "awaiting_hash"

            if ADMIN_CHAT_ID:
                try:
                    if update.message.photo:
                        await context.bot.send_photo(
                            chat_id=ADMIN_CHAT_ID,
                            photo=update.message.photo[-1].file_id,
                            caption=f"📸 Screenshot for Order `{order_id}` from {user.full_name} (@{user.username})",
                            parse_mode="Markdown"
                        )
                    else:
                        await context.bot.send_document(
                            chat_id=ADMIN_CHAT_ID,
                            document=update.message.document.file_id,
                            caption=f"📸 Screenshot for Order `{order_id}` from {user.full_name} (@{user.username})",
                            parse_mode="Markdown"
                        )
                except:
                    pass

            await update.message.reply_text(
                "✅ *Screenshot received!*\n\n"
                "🔗 *Now please enter your Transaction Hash ID:*\n\n"
                "_You can find this in your wallet's transaction history._",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "📸 *Please send a screenshot (image) of your payment.*",
                parse_mode="Markdown"
            )

    # ── HASH ID ──
    elif state == "awaiting_hash":
        hash_id = text_in
        order_id = context.user_data.get("order_id")
        coin = context.user_data.get("coin")
        network = context.user_data.get("network")
        amount_usd = context.user_data.get("amount_usd")
        address = context.user_data.get("address")
        context.user_data["state"] = "verifying"

        await update.message.reply_text(
            f"⏳ *Verifying your transaction...*\n\n"
            f"🔗 Hash: `{hash_id}`\n\n"
            f"_This usually takes a few seconds._",
            parse_mode="Markdown"
        )

        verified, msg = await verify_transaction(hash_id, coin, network, amount_usd, address)

        if verified:
            if order_id in orders_store:
                orders_store[order_id]["status"] = "verified"
                orders_store[order_id]["hash"] = hash_id

            if ADMIN_CHAT_ID:
                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=(
                        f"✅ *Transaction Verified!*\n\n"
                        f"🔖 Order ID: `{order_id}`\n"
                        f"👤 {user.full_name} (@{user.username})\n"
                        f"💎 {coin} ({network})\n"
                        f"💵 ${amount_usd} \u2192 \u20b9{context.user_data.get('amount_inr')}\n"
                        f"🔗 Hash: `{hash_id}`\n"
                        f"🏦 Pay to: {context.user_data.get('pay_detail')}\n\n"
                        f"👇 Click below once you've sent the payment:"
                    ),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ Mark as Paid", callback_data=f"admin_paid_{order_id}")]
                    ])
                )

            await update.message.reply_text(
                f"✅ *Transaction Verified!*\n\n"
                f"🎉 Your order `{order_id}` is confirmed!\n\n"
                f"💸 We are processing your INR payment now.\n"
                f"You'll be notified once it's sent.\n\n"
                f"⏱️ _Usually takes 5–15 minutes._",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard()
            )
        else:
            context.user_data["state"] = "awaiting_hash"
            await update.message.reply_text(
                f"❌ *Verification Failed*\n\n"
                f"_{msg}_\n\n"
                f"Please check your hash and try again, or contact @itsmer4",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Again", callback_data="retry_hash")],
                    [InlineKeyboardButton("📞 Support", callback_data="support")]
                ])
            )

    else:
        caption = (
            f"👋 *Welcome back, {user.first_name}!*\n\n"
            "⬇️ Choose an option below:"
        )
        await send_photo(update.message.chat, "Homepage_image.jpeg", caption, main_menu_keyboard())

# ─── BLOCKCHAIN VERIFICATION ──────────────────────────────────────────────────
async def verify_transaction(hash_id, coin, network, amount_usd, expected_address):
    if coin in ["USDT", "TRON"] and network == "TRC20":
        return await verify_tron(hash_id, expected_address)
    elif coin == "BTC":
        return await verify_btc(hash_id, expected_address)
    elif coin in ["ETH", "USDT", "USDC", "BNB"] and network in ["ERC20", "BEP20"]:
        return await verify_evm(hash_id, expected_address, network)
    elif coin in ["SOL", "USDT", "USDC"] and network in ["Solana", "SOL"]:
        return await verify_solana(hash_id, expected_address)
    elif coin == "TON" or network == "TON":
        return await verify_ton(hash_id, expected_address)
    elif coin == "LTC":
        return await verify_ltc(hash_id, expected_address)
    else:
        return False, "Unsupported coin/network. Please contact support at @itsmer4"

async def verify_tron(hash_id, expected_address):
    try:
        url = f"https://api.trongrid.io/v1/transactions/{hash_id}"
        r = requests.get(url, timeout=10)
        data = r.json()
        if data.get("data") and len(data["data"]) > 0:
            tx = data["data"][0]
            if tx.get("ret", [{}])[0].get("contractRet") == "SUCCESS":
                raw_data = tx.get("raw_data", {})
                contract = raw_data.get("contract", [{}])[0]
                param = contract.get("parameter", {}).get("value", {})
                to_address = param.get("to_address", "")
                if not to_address or expected_address.lower() in to_address.lower():
                    return True, "Verified on TRON"
                return False, "Transaction destination does not match our wallet."
        return False, "Transaction not found or failed on TRON network."
    except Exception as e:
        logger.error(f"TRON verify error: {e}")
        return False, "Could not verify on TRON. Please check your hash and try again."

async def verify_btc(hash_id, expected_address):
    try:
        url = f"https://api.blockcypher.com/v1/btc/main/txs/{hash_id}"
        r = requests.get(url, timeout=10)
        data = r.json()
        if "confirmations" in data and data["confirmations"] >= 1:
            for out in data.get("outputs", []):
                if expected_address in out.get("addresses", []):
                    return True, "Verified on Bitcoin"
            return False, "Transaction found but destination does not match our wallet."
        return False, "Transaction unconfirmed or not found on Bitcoin network."
    except Exception as e:
        logger.error(f"BTC verify error: {e}")
        return False, "Could not verify on Bitcoin. Please check your hash and try again."

async def verify_evm(hash_id, expected_address, network):
    try:
        if network == "BEP20":
            url = f"https://api.bscscan.com/api?module=proxy&action=eth_getTransactionByHash&txhash={hash_id}&apikey=YourApiKeyToken"
        else:
            url = f"https://api.etherscan.io/api?module=proxy&action=eth_getTransactionByHash&txhash={hash_id}&apikey=YourApiKeyToken"
        r = requests.get(url, timeout=10)
        data = r.json()
        tx = data.get("result")
        if tx and tx.get("hash"):
            return True, f"Verified on {network}"
        return False, f"Transaction not found on {network} network."
    except Exception as e:
        logger.error(f"EVM verify error: {e}")
        return False, f"Could not verify on {network}. Please check your hash and try again."

async def verify_solana(hash_id, expected_address):
    try:
        url = "https://api.mainnet-beta.solana.com"
        payload = {
            "jsonrpc": "2.0", "id": 1,
            "method": "getTransaction",
            "params": [hash_id, {"encoding": "json", "maxSupportedTransactionVersion": 0}]
        }
        r = requests.post(url, json=payload, timeout=10)
        data = r.json()
        result = data.get("result")
        if result and not result.get("meta", {}).get("err"):
            return True, "Verified on Solana"
        return False, "Transaction not found or failed on Solana."
    except Exception as e:
        logger.error(f"SOL verify error: {e}")
        return False, "Could not verify on Solana. Please check your hash and try again."

async def verify_ton(hash_id, expected_address):
    try:
        url = f"https://tonapi.io/v2/blockchain/transactions/{hash_id}"
        r = requests.get(url, timeout=10)
        data = r.json()
        if data.get("hash") or data.get("lt"):
            return True, "Verified on TON"
        return False, "Transaction not found on TON network."
    except Exception as e:
        logger.error(f"TON verify error: {e}")
        return False, "Could not verify on TON. Please check your hash and try again."

async def verify_ltc(hash_id, expected_address):
    try:
        url = f"https://api.blockcypher.com/v1/ltc/main/txs/{hash_id}"
        r = requests.get(url, timeout=10)
        data = r.json()
        if "confirmations" in data and data["confirmations"] >= 1:
            for out in data.get("outputs", []):
                if expected_address in out.get("addresses", []):
                    return True, "Verified on Litecoin"
            return False, "Transaction found but destination does not match our wallet."
        return False, "Transaction unconfirmed or not found on Litecoin."
    except Exception as e:
        logger.error(f"LTC verify error: {e}")
        return False, "Could not verify on Litecoin. Please check your hash and try again."

# ─── ADMIN SETUP ──────────────────────────────────────────────────────────────
async def setup_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ADMIN_CHAT_ID
    user = update.effective_user
    if f"@{user.username}" == ADMIN_USERNAME:
        ADMIN_CHAT_ID = user.id
        await update.message.reply_text(
            f"✅ Admin registered! You'll receive all notifications here.\n"
            f"Your Chat ID: `{user.id}`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ You are not authorized.")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", setup_admin))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))
    print("🤖 Crypto Exchange Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
