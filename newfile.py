# -*- coding: utf-8 -*-
import logging
import uuid
from datetime import date
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatMember
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

# --- Configuration ---
BOT_TOKEN = "7157173991:AAGAoodpZ1867RjOBbR0VAkONfVU9q-mRRo"  # Replace with your bot token
BOT_USERNAME = "@ReferKroEarnKroBot"  # Replace with your bot's username (e.g., MyReferBot, without @)

# Channel details (Bot MUST be an ADMIN in this channel)
REQUIRED_CHANNEL_ID = "@referkroearnkro2"  # The channel username (public) or ID (private)
REQUIRED_CHANNEL_LINK = "https://t.me/referkroearnkro2"

REFERRAL_BONUS = 5
DAILY_BONUS_AMOUNT = 1
WITHDRAWAL_THRESHOLD = 100

# --- In-memory Data Storage ---
# { user_id: {"username": "tg_username", "balance": 0, "referral_code": "xyz", "referred_by": None/referrer_id, "last_daily_bonus": None/date_obj} }
user_data = {}
# { referral_code: user_id }
referral_code_map = {}

# --- Logging Setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Helper Functions ---

def get_user_record(user_id: int, username: str = None) -> dict:
    """Gets or creates a user record."""
    if user_id not in user_data:
        referral_code = str(uuid.uuid4().hex)[:8]
        while referral_code in referral_code_map: # Ensure uniqueness
            referral_code = str(uuid.uuid4().hex)[:8]

        user_data[user_id] = {
            "username": username,
            "balance": 0,
            "referral_code": referral_code,
            "referred_by": None,
            "last_daily_bonus": None,
        }
        referral_code_map[referral_code] = user_id
        logger.info(f"New user registered: {user_id} ({username}) with referral code {referral_code}")
    elif username and user_data[user_id]["username"] != username:
        user_data[user_id]["username"] = username # Update username if changed
    return user_data[user_id]

async def is_user_member_of_channel(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if the user is a member of the required channel. Bot needs to be admin."""
    if not REQUIRED_CHANNEL_ID:
        logger.warning("REQUIRED_CHANNEL_ID not set. Skipping channel membership check.")
        return True

    try:
        member_status = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL_ID, user_id=user_id)
        logger.debug(f"User {user_id} in channel {REQUIRED_CHANNEL_ID} status: {member_status.status}")
        # Valid statuses: creator, administrator, member, owner (for ChatMember.OWNER if using newer PTB versions)
        return member_status.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.CREATOR, "owner"]
    except BadRequest as e:
        error_message = str(e).lower()
        if "user not found" in error_message or "member not found" in error_message:
            logger.info(f"User {user_id} not found in channel {REQUIRED_CHANNEL_ID}.")
            return False
        elif "chat not found" in error_message:
            logger.error(f"CRITICAL: Channel {REQUIRED_CHANNEL_ID} not found or bot has no access. Ensure bot is ADMIN.")
            return False # Cannot proceed if channel is misconfigured
        elif "bot is not a member" in error_message or "not enough rights" in error_message:
             logger.error(f"CRITICAL: Bot is not an admin or member of {REQUIRED_CHANNEL_ID}. Cannot check memberships.")
             return False # Cannot proceed if bot is misconfigured
        logger.error(f"BadRequest checking channel membership for {user_id} in {REQUIRED_CHANNEL_ID}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking channel membership for {user_id} in {REQUIRED_CHANNEL_ID}: {e}")
        return False

def generate_join_channel_keyboard() -> InlineKeyboardMarkup:
    """Generates keyboard for joining the channel."""
    keyboard = [
        [InlineKeyboardButton("➡️ Join Our Channel", url=REQUIRED_CHANNEL_LINK)],
        [InlineKeyboardButton("✅ I Have Joined", callback_data="check_join_status")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def send_join_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, edit_message: bool = False):
    """Sends or edits message prompting user to join the channel."""
    text = (
        f"👋 **Welcome!**\n\n"
        f"To use this bot and access its features, you must first join our official Telegram channel:\n"
        f"{https://t.me/referkroearnkro2}\n\n"
        "After joining, please click the 'I Have Joined' button below."
    )
    reply_markup = generate_join_channel_keyboard()

    if edit_message and update.callback_query:
        try:
            await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        except BadRequest as e:
            if "Message is not modified" not in str(e).lower():
                logger.error(f"Error editing message for join prompt: {e}")
            await update.callback_query.answer("Please join our channel first and then click 'I Have Joined'.")
    elif update.message:
        await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    elif update.callback_query: # Fallback if called from callback without edit_message
        await update.callback_query.message.reply_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


def generate_main_keyboard_2x2() -> InlineKeyboardMarkup:
    """Generates the main 2x2 inline keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("💰 My Balance", callback_data="balance"),
            InlineKeyboardButton("🔗 My Referral", callback_data="referral_info")
        ],
        [
            InlineKeyboardButton("💸 Withdraw Funds", callback_data="withdraw"),
            InlineKeyboardButton("💡 How to Earn?", callback_data="earn_methods")
        ],
        [InlineKeyboardButton("🎁 Daily Bonus", callback_data="daily_bonus")]
    ]
    return InlineKeyboardMarkup(keyboard)

def generate_submenu_keyboard() -> InlineKeyboardMarkup:
    """Generates a keyboard with a back button for submenus."""
    keyboard = [[InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")]]
    return InlineKeyboardMarkup(keyboard)

async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None, edit_message: bool = False):
    """Sends or edits the main menu message."""
    user = update.effective_user
    get_user_record(user.id, user.username or user.first_name) # Ensure record exists

    message_text = text if text else "🛠️ **Main Menu**\n\nSelect an option:"
    reply_markup = generate_main_keyboard_2x2()

    if edit_message and update.callback_query:
        try:
            await update.callback_query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        except BadRequest as e:
            if "Message is not modified" not in str(e).lower():
                logger.warning(f"Could not edit message to main menu: {e}")
            await update.callback_query.answer() # Acknowledge if not modified
    elif update.message:
        await update.message.reply_text(text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    elif update.callback_query: # Fallback for callback if edit_message is False (e.g., after successful join)
        await update.callback_query.message.reply_text(text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


# --- Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command, channel join check, and referral processing."""
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    args = context.args

    # Create user record first, important for referral logic to know if user is "new" for referral purpose
    get_user_record(user_id, username)

    # --- Channel Join Check ---
    if not await is_user_member_of_channel(user_id, context):
        await send_join_prompt(update, context, edit_message=False) # Send as new message
        return
    # --- End Channel Join Check ---

    welcome_message_parts = []
    # Check if this specific user account has been referred before OR if it's not the only user (simple heuristic for existing user)
    is_returning_user = user_data[user_id].get("referred_by") is not None or len(user_data) > 1 and not args

    if is_returning_user:
        welcome_message_parts.append(f"🎉 Welcome back, {user.first_name}!")
    else:
        welcome_message_parts.append(f"👋 Hello, {user.first_name}!")

    # Process referral if 'start' payload exists
    if args and len(args) > 0:
        referrer_code = args[0]
        if referrer_code in referral_code_map:
            referrer_id = referral_code_map[referrer_code]
            if referrer_id != user_id:
                # Only give bonus if this user hasn't been referred before
                if user_data[user_id].get("referred_by") is None:
                    user_data[user_id]["referred_by"] = referrer_id
                    referrer_record = get_user_record(referrer_id) # Ensure referrer exists & get their data
                    referrer_record["balance"] += REFERRAL_BONUS
                    logger.info(f"User {referrer_id} ({referrer_record.get('username')}) earned ₹{REFERRAL_BONUS} for referring {user_id} ({username})")
                    try:
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=f"🎉 Congratulations! {username or 'A new user'} joined using your referral link. You've earned ₹{REFERRAL_BONUS}!"
                        )
                    except Exception as e:
                        logger.error(f"Failed to send referral bonus notification to {referrer_id}: {e}")
                    welcome_message_parts.append(f"You were successfully referred by {referrer_record.get('username', 'a current user')}!")
                else: # Already referred
                    welcome_message_parts.append("You've already been referred or started. Thanks for clicking the link!")
            else: # Referring self
                welcome_message_parts.append("Nice try! You can't refer yourself. 😉")
        else: # Invalid referral code
            welcome_message_parts.append("Invalid referral code provided.")
    elif not is_returning_user and not user_data[user_id].get("referred_by"): # Truly new user, no args
         welcome_message_parts.append("Explore the options below to get started.")


    final_welcome_message = "\n\n".join(filter(None, welcome_message_parts))
    await send_main_menu(update, context, text=final_welcome_message, edit_message=False) # Send as new after start

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays help information."""
    # First, check if user is member of channel
    if not await is_user_member_of_channel(update.effective_user.id, context):
        await send_join_prompt(update, context, edit_message=False)
        return

    help_text = (
        "**🤖 Bot Guide**\n\n"
        "Use the buttons to navigate:\n"
        "- `/start`: Access the main menu.\n"
        "- **My Balance**: View your current earnings.\n"
        "- **My Referral**: Get your unique referral link and stats.\n"
        "- **Withdraw Funds**: Request withdrawal (min. ₹{WITHDRAWAL_THRESHOLD}). This is a simulated process.\n"
        "- **How to Earn?**: Details on referral bonuses & daily rewards.\n"
        "- **Daily Bonus**: Claim your daily ₹{DAILY_BONUS_AMOUNT}.\n\n"
        f"🔗 **Our Community Channel:**\n"
        f"- Telegram: {https://t.me/referkroearnkro2}\n\n"
        "Make sure you've joined the channel to use all features!"
    )
    await update.message.reply_text(
        help_text.format(WITHDRAWAL_THRESHOLD=WITHDRAWAL_THRESHOLD, DAILY_BONUS_AMOUNT=DAILY_BONUS_AMOUNT),
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

# --- Callback Query Handler ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles all inline keyboard button presses."""
    query = update.callback_query
    await query.answer() # Acknowledge the button press immediately

    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    record = get_user_record(user_id, username) # Ensure user record exists

    # --- Channel Join Check Gate (for all actions except checking join status itself) ---
    if query.data != "check_join_status":
        is_member = await is_user_member_of_channel(user_id, context)
        if not is_member:
            await send_join_prompt(update, context, edit_message=True) # Try to edit current message
            return
    # --- End Channel Join Check Gate ---

    # --- Handle specific button actions ---
    if query.data == "check_join_status":
        if await is_user_member_of_channel(user_id, context):
            await query.edit_message_text("✅ Thank you for joining! You now have full access to the bot.")
            # Automatically show main menu after successful join check
            await send_main_menu(update, context, text="Welcome! Here's the main menu:", edit_message=False) # Send as new message
        else:
            await query.answer("It seems you haven't joined the channel yet, or I couldn't verify your membership. Please ensure you've joined and try again.", show_alert=True)

    elif query.data == "main_menu":
        await send_main_menu(update, context, edit_message=True)

    elif query.data == "balance":
        text = f"💰 **Your Balance**\n\nYour current earnings: **₹{record['balance']}**"
        await query.edit_message_text(text=text, reply_markup=generate_submenu_keyboard(), parse_mode=ParseMode.MARKDOWN)

    elif query.data == "referral_info":
        referral_link = f"https://t.me/{BOT_USERNAME}?start={record['referral_code']}"
        # Count successful referrals
        num_referred = sum(1 for u_id, data in user_data.items() if data.get("referred_by") == user_id)

        text = (
            f"🔗 **Your Referral Corner**\n\n"
            f"Share your unique referral link below. For every *new* user who starts the bot through your link "
            f"(and joins our channel), you earn **₹{REFERRAL_BONUS}**!\n\n"
            f"Your Link:\n`{referral_link}`\n\n" # Use MarkdownV2 for code block
            f"👥 Users Successfully Referred: **{num_referred}**\n"
            f"💸 Earnings from Referrals: **₹{num_referred * REFERRAL_BONUS}**"
        )
        await query.edit_message_text(text=text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=generate_submenu_keyboard())

    elif query.data == "withdraw":
        text = f"💸 **Withdraw Funds**\n\nYour current balance: **₹{record['balance']}**\nMinimum for withdrawal: **₹{WITHDRAWAL_THRESHOLD}**\n\n"
        if record["balance"] >= WITHDRAWAL_THRESHOLD:
            # In a real bot, you'd add a "Confirm Withdrawal" button or ask for payment info.
            # For this simulation, we just inform.
            text += "You are eligible for withdrawal!\n\n**This is a simulated withdrawal process.** " \
                    "In a real bot, we would now ask for your payment details. " \
                    "For now, your balance remains unchanged after viewing this message."
            # To actually deduct (example, would need more robust handling):
            # record['balance'] = 0 # or record['balance'] -= amount_withdrawn
            # logger.info(f"User {user_id} withdrawal processed (simulated). New balance: ₹{record['balance']}")
        else:
            text += f"You need **₹{WITHDRAWAL_THRESHOLD - record['balance']:.2f}** more to be eligible for withdrawal."
        await query.edit_message_text(text=text, reply_markup=generate_submenu_keyboard(), parse_mode=ParseMode.MARKDOWN)

    elif query.data == "earn_methods":
        earn_text = (
            "💡 **How to Earn with Us?**\n\n"
            f"1.  **Refer & Earn (₹{REFERRAL_BONUS}/Referral)**:\n"
            f"    - Get your unique link from the 'My Referral' section.\n"
            f"    - Share it with friends. When a *new* user starts the bot using your link AND joins our "
            f"      mandatory channel ({REQUIRED_CHANNEL_ID}), you get **₹{REFERRAL_BONUS}** credited to your balance.\n\n"
            f"2.  **Daily Bonus (₹{DAILY_BONUS_AMOUNT})**:\n"
            f"    - Visit the 'Daily Bonus' section from the main menu once every 24 hours to claim **₹{DAILY_BONUS_AMOUNT}**.\n\n"
            f"🔗 **Our Community Channel (Mandatory to Join):**\n"
            f"- Telegram: {https://t.me/referkroearnkro2}\n\n"
            "Stay active, invite more, and earn more!"
        )
        await query.edit_message_text(text=earn_text, parse_mode=ParseMode.MARKDOWN, reply_markup=generate_submenu_keyboard(), disable_web_page_preview=True)

    elif query.data == "daily_bonus":
        today = date.today()
        text = ""
        if record.get("last_daily_bonus") == today:
            text = "✋ You've already claimed your daily bonus today. Please try again tomorrow!"
        else:
            record["balance"] += DAILY_BONUS_AMOUNT
            record["last_daily_bonus"] = today
            logger.info(f"User {user_id} claimed daily bonus of ₹{DAILY_BONUS_AMOUNT}. New balance: ₹{record['balance']}")
            text = f"🎉 Daily Bonus Claimed!\n\nYou've successfully received **₹{DAILY_BONUS_AMOUNT}**.\nYour new balance is **₹{record['balance']}**."
        # Daily bonus is a direct action, so we go back to main menu after showing status
        await query.edit_message_text(text=text, parse_mode=ParseMode.MARKDOWN, reply_markup=generate_main_keyboard_2x2())


# --- Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        # Avoid sending error if the original error was about message not modified or user not found in channel etc.
        if isinstance(context.error, BadRequest):
            err_str = str(context.error).lower()
            if "message is not modified" in err_str or \
               "user not found" in err_str or \
               "member not found" in err_str or \
               "chat not found" in err_str or \
               "bot is not a member" in err_str:
                return # These are handled or expected in some flows.
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="😕 Oops! An unexpected error occurred on my end. Please try again in a moment. If the problem persists, you can try /start again or contact support."
            )
        except Exception as e:
            logger.error(f"Failed to send error message to user {update.effective_chat.id}: {e}")


# --- Main Function ---
def main() -> None:
    """Start the bot."""
    if BOT_TOKEN == "7157173991:AAGAoodpZ1867RjOBbR0VAkONfVU9q-mRRo" or BOT_USERNAME == "@ReferKroEarnKroBot":
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! CRITICAL: SET YOUR BOT_TOKEN and BOT_USERNAME in the script.                       !!!")
        print("!!! ALSO, ENSURE THE BOT (@YourBotUsername) IS AN ADMINISTRATOR IN THE CHANNEL           !!!")
        print(f"!!! SPECIFIED BY REQUIRED_CHANNEL_ID ('{REQUIRED_CHANNEL_ID}') FOR THE JOIN CHECK TO WORK! !!!")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        return

    if not REQUIRED_CHANNEL_ID or not REQUIRED_CHANNEL_LINK:
        print("!!! WARNING: REQUIRED_CHANNEL_ID or REQUIRED_CHANNEL_LINK is not set. Channel join check will fail. !!!")
        return


    application = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))

    # Callback query handler for inline buttons
    application.add_handler(CallbackQueryHandler(button_callback))

    # Error handler
    application.add_error_handler(error_handler)

    logger.info(f"Bot @{BOT_USERNAME} is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES) # Process all types of updates
    logger.info(f"Bot @{BOT_USERNAME} has stopped.")

if __name__ == "__main__":
    main()