import sys
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# Load environment variables
load_dotenv()

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Bot and database configuration
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MONGO_URI = os.getenv('MONGO_URI')
DB_NAME = os.getenv('DB_NAME')

bot = TeleBot(TOKEN)

# Global variables
db_available = False
users = None
audit = None

def connect_mongodb():
    global db_available, users, audit
    try:
        client = MongoClient(MONGO_URI)
        client.admin.command('ismaster')
        logger.info("Successful connection to MongoDB")
        db = client[DB_NAME]
        
        if 'users' not in db.list_collection_names():
            db.create_collection('users')
            logger.info("Collection 'users' created successfully.")
        users = db['users']
        
        if 'audit' not in db.list_collection_names():
            db.create_collection('audit')
            logger.info("Collection 'audit' created successfully.")
        audit = db['audit']
        
        db_available = True
        return client, db
    except ConnectionFailure:
        logger.error("Failed to connect to MongoDB. Check if the MongoDB service is running.")
        db_available = False
        return None, None

client, db = connect_mongodb()

def register_audit(chat_id, operation_type, amount, previous_balance, current_balance):
    if not db_available:
        logger.error("Failed to register audit: database unavailable")
        return
    
    record = {
        'chat_id': chat_id,
        'operation_type': operation_type,
        'amount': amount,
        'previous_balance': previous_balance,
        'current_balance': current_balance,
        'timestamp': datetime.now()
    }
    
    try:
        audit.insert_one(record)
        logger.info(f"Audit record created: {record}")
    except Exception as e:
        logger.error(f"Error creating audit record: {e}")

def generate_markup(buttons):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    for text, callback_data in buttons:
        markup.add(InlineKeyboardButton(text, callback_data=callback_data))
    return markup

def generate_initial_markup():
    buttons = [
        ("Check Balance", "check_balance"),
        ("Deposit", "deposit"),
        ("Withdraw", "withdraw"),
        ("History", "history"),
        ("Add Payment Method", "add_method")
    ]
    return generate_markup(buttons)

@bot.message_handler(commands=['start'])
def handle_start(message):
    if not db_available:
        bot.reply_to(message, "Oops, our database is experiencing instability. Please contact support.")
        return

    chat_id = message.chat.id
    user = users.find_one({'_id': chat_id})
    if not user:
        users.insert_one({
            '_id': chat_id,
            'balance': 0,
            'last_transaction': None,
            'payment_methods': {}
        })
        logger.info(f"New user registered: {chat_id}")
    bot.reply_to(message, "Welcome to the Bank Bot! What would you like to do?", reply_markup=generate_initial_markup())

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if not db_available:
        bot.answer_callback_query(call.id, "Sorry, the service is temporarily unavailable. Please try again later.")
        return

    chat_id = call.message.chat.id
    data = call.data.split("_")

    if data[0] == "check":
        check_balance(call.message)
    elif data[0] == "deposit":
        if len(data) > 1:
            amount = float(data[2])
            confirm_deposit(call.message, amount)
        else:
            start_deposit(call.message)
    elif data[0] == "withdraw":
        if len(data) > 1:
            amount = float(data[2])
            confirm_withdrawal(call.message, amount)
        else:
            start_withdrawal(call.message)
    elif data[0] == "history":
        show_history(call.message)
    elif data[0] == "add":
        if data[1] == "method":
            add_method(call.message)
        elif data[1] == "crypto":
            start_crypto_deposit(call.message, data[2])
    elif data[0] in ["bank", "paypal", "crypto"]:
        if data[1] == "transfer":
            bot.send_message(chat_id, f"You selected Bank Transfer. Please enter the bank name (e.g., Itaú):")
            bot.register_next_step_handler(call.message, ask_for_bank_name)
        elif data[0] == "paypal":
            bot.send_message(chat_id, "Please enter your PayPal email:")
            bot.register_next_step_handler(call.message, ask_for_paypal_email)
        elif data[0] == "crypto":
            bot.send_message(chat_id, "Select the cryptocurrency you want to add:", reply_markup=generate_crypto_markup(chat_id))
    elif data[0] == "cancel":
        bot.send_message(chat_id, "Operation cancelled.", reply_markup=generate_initial_markup())
        logger.info(f"Operation cancelled by user: {chat_id}")

def check_balance(message):
    if not db_available:
        bot.send_message(message.chat.id, "Oops, our database is experiencing instability. Please contact support.")
        return

    chat_id = message.chat.id
    user = users.find_one({'_id': chat_id})
    if user:
        balance = user['balance']
        last_transaction = user['last_transaction']
        if last_transaction:
            response = (f"Your current balance is: ${balance:.2f}\n\n"
                        f"Last transaction: {last_transaction['type']} of ${last_transaction['amount']:.2f} on {last_transaction['date']}")
        else:
            response = f"Your current balance is: ${balance:.2f}\n\nYou haven't made any transactions yet."
    else:
        response = "Sorry, we couldn't find your information. Please try again later."
    
    bot.send_message(chat_id, response, reply_markup=generate_initial_markup())
    logger.info(f"Balance checked for user: {chat_id}")

def add_method(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "Select the payment method you want to add:", reply_markup=generate_payment_methods_markup(chat_id, "add_method"))

def generate_payment_methods_markup(chat_id, operation_type):
    buttons = [
        ("Bank Transfer", f"bank_transfer_{chat_id}"),
        ("PayPal", f"paypal_{chat_id}"),
        ("Cryptocurrency", f"crypto_{chat_id}")
    ]
    return generate_markup(buttons)

def generate_crypto_markup(chat_id):
    buttons = [
        ("BTC", f"add_crypto_BTC_{chat_id}"),
        ("ETH", f"add_crypto_ETH_{chat_id}"),
        ("USDT", f"add_crypto_USDT_{chat_id}")
    ]
    return generate_markup(buttons)

def ask_for_bank_name(message):
    chat_id = message.chat.id
    bank_name = message.text
    save_bank_method(chat_id, bank_name)

def save_bank_method(chat_id, bank_name):
    users.update_one({'_id': chat_id}, {'$addToSet': {'payment_methods.bank_transfer': bank_name}})
    bot.send_message(chat_id, f"Bank transfer method '{bank_name}' added successfully!")
    show_added_payment_method(chat_id, "bank_transfer", bank_name)

def ask_for_paypal_email(message):
    chat_id = message.chat.id
    paypal_email = message.text
    save_paypal_method(chat_id, paypal_email)

def save_paypal_method(chat_id, paypal_email):
    users.update_one({'_id': chat_id}, {'$addToSet': {'payment_methods.paypal': paypal_email}})
    bot.send_message(chat_id, f"PayPal method '{paypal_email}' added successfully!")
    show_added_payment_method(chat_id, "paypal", paypal_email)

def show_added_payment_method(chat_id, method_type, method_name):
    buttons = [(method_name, f"{method_type}_{method_name}_{chat_id}")]
    markup = generate_markup(buttons)
    bot.send_message(chat_id, f"You can now use the method '{method_name}' for deposits.", reply_markup=markup)

def start_deposit(message):
    if not db_available:
        bot.send_message(message.chat.id, "Oops, our database is experiencing instability. Please contact support.")
        return

    bot.send_message(message.chat.id, "Please enter the amount you want to deposit:")
    bot.register_next_step_handler(message, process_deposit_amount)

def process_deposit_amount(message):
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError("The amount must be greater than zero.")
        
        chat_id = message.chat.id
        user = users.find_one({'_id': chat_id})
        current_balance = user['balance']
        
        buttons = [
            ("Confirm", f"deposit_{amount}"),
            ("Cancel", "cancel_operation")
        ]
        markup = generate_markup(buttons)
        bot.send_message(chat_id, f"You want to deposit ${amount:.2f}. Your current balance is ${current_balance:.2f}. Confirm?", reply_markup=markup)
    except ValueError as e:
        bot.send_message(message.chat.id, f"Invalid amount. Please try again.")
        bot.register_next_step_handler(message, process_deposit_amount)

def confirm_deposit(message, amount):
    chat_id = message.chat.id
    timestamp = datetime.now()
    
    user = users.find_one({'_id': chat_id})
    previous_balance = user['balance']
    
    result = users.update_one(
        {'_id': chat_id},
        {
            '$inc': {'balance': amount},
            '$set': {
                'last_transaction': {
                    'type': 'deposit',
                    'amount': amount,
                    'date': timestamp.strftime("%d/%m/%Y %H:%M:%S")}}})
    
    if result.modified_count > 0:
        updated_balance = previous_balance + amount
        response = (f"Deposit of ${amount:.2f} successful!\n"
                    f"Previous balance: ${previous_balance:.2f}\n"
                    f"Updated balance: ${updated_balance:.2f}\n"
                    f"Transaction date and time: {timestamp.strftime('%d/%m/%Y %H:%M:%S')}")
        bot.send_message(chat_id, response, reply_markup=generate_initial_markup())
        logger.info(f"Deposit made: User {chat_id}, Amount ${amount:.2f}, Previous balance ${previous_balance:.2f}, New balance ${updated_balance:.2f}")
        
        register_audit(chat_id, "deposit", amount, previous_balance, updated_balance)
    else:
        bot.send_message(chat_id, "An error occurred while processing the deposit. Please try again.", reply_markup=generate_initial_markup())
        logger.error(f"Failed to process deposit: User {chat_id}, Amount ${amount:.2f}")

def start_withdrawal(message):
    if not db_available:
        bot.send_message(message.chat.id, "Oops, our database is experiencing instability. Please contact support.")
        return

    chat_id = message.chat.id
    user = users.find_one({'_id': chat_id})
    current_balance = user['balance']

    bot.send_message(chat_id, f"Your current balance is ${current_balance:.2f}. Please enter the amount you want to withdraw:")
    bot.register_next_step_handler(message, process_withdrawal_amount)

def process_withdrawal_amount(message):
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError("The amount must be greater than zero.")
        
        chat_id = message.chat.id
        user = users.find_one({'_id': chat_id})
        current_balance = user['balance']
        
        if current_balance < amount:
            bot.send_message(chat_id, f"Insufficient balance. Your current balance is ${current_balance:.2f}. Please enter a new withdrawal amount:")
            bot.register_next_step_handler(message, process_withdrawal_amount)
            return
        
        buttons = [
            ("Confirm", f"withdraw_{amount}"),
            ("Cancel", "cancel_operation")
        ]
        markup = generate_markup(buttons)
        bot.send_message(chat_id, f"You want to withdraw ${amount:.2f}. Your current balance is ${current_balance:.2f}. Confirm?", reply_markup=markup)
    except ValueError as e:
        bot.send_message(message.chat.id, "Invalid amount. Please try again.")
        bot.register_next_step_handler(message, process_withdrawal_amount)

def confirm_withdrawal(message, amount):
    chat_id = message.chat.id
    timestamp = datetime.now()
    
    user = users.find_one({'_id': chat_id})
    previous_balance = user['balance']
    
    result = users.update_one(
        {'_id': chat_id},
        {
            '$inc': {'balance': -amount},
            '$set': {
                'last_transaction': {
                    'type': 'withdrawal',
                    'amount': amount,
                    'date': timestamp.strftime("%d/%m/%Y %H:%M:%S")}}})
    
    if result.modified_count > 0:
        updated_balance = previous_balance - amount
        response = (f"Withdrawal of ${amount:.2f} successful!\n"
                    f"Previous balance: ${previous_balance:.2f}\n"
                    f"Updated balance: ${updated_balance:.2f}\n"
                    f"Transaction date and time: {timestamp.strftime('%d/%m/%Y %H:%M:%S')}")
        bot.send_message(chat_id, response, reply_markup=generate_initial_markup())
        logger.info(f"Withdrawal made: User {chat_id}, Amount ${amount:.2f}, Previous balance ${previous_balance:.2f}, New balance ${updated_balance:.2f}")
        
        register_audit(chat_id, "withdrawal", amount, previous_balance, updated_balance)
    else:
        bot.send_message(chat_id, "An error occurred while processing the withdrawal. Please try again.", reply_markup=generate_initial_markup())
        logger.error(f"Failed to process withdrawal: User {chat_id}, Amount ${amount:.2f}")

def start_crypto_deposit(message, crypto_type):
    chat_id = message.chat.id
    bot.send_message(chat_id, f"You selected {crypto_type}. Please enter the amount you want to deposit:")
    bot.register_next_step_handler(message, lambda msg: process_crypto_deposit_amount(msg, crypto_type))

def process_crypto_deposit_amount(message, crypto_type):
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError("The amount must be greater than zero.")
        
        chat_id = message.chat.id
        user = users.find_one({'_id': chat_id})
        current_balance = user['balance']
        
        buttons = [
            ("Confirm", f"confirm_crypto_deposit_{crypto_type}_{amount}"),
            ("Cancel", "cancel_operation")
        ]
        markup = generate_markup(buttons)
        bot.send_message(chat_id, f"You want to deposit {amount} {crypto_type}. Your current balance is ${current_balance:.2f}. Confirm?", reply_markup=markup)
    except ValueError as e:
        bot.send_message(message.chat.id, f"Invalid amount. Please try again.")
        bot.register_next_step_handler(message, lambda msg: process_crypto_deposit_amount(msg, crypto_type))

def confirm_crypto_deposit(message, crypto_type, amount):
    chat_id = message.chat.id
    timestamp = datetime.now()
    
    user = users.find_one({'_id': chat_id})
    previous_balance = user['balance']
    
    # For simplicity, we're treating all crypto as USD 1:1
    # In a real application, you'd need to implement exchange rates
    usd_amount = amount
    
    result = users.update_one(
        {'_id': chat_id},
        {
            '$inc': {'balance': usd_amount},
            '$set': {
                'last_transaction': {
                    'type': f'{crypto_type}_deposit',
                    'amount': amount,
                    'date': timestamp.strftime("%d/%m/%Y %H:%M:%S")}}})
    
    if result.modified_count > 0:
        updated_balance = previous_balance + usd_amount
        response = (f"{crypto_type} deposit of {amount} (${usd_amount:.2f}) successful!\n"
                    f"Previous balance: ${previous_balance:.2f}\n"
                    f"Updated balance: ${updated_balance:.2f}\n"
                    f"Transaction date and time: {timestamp.strftime('%d/%m/%Y %H:%M:%S')}")
        bot.send_message(chat_id, response, reply_markup=generate_initial_markup())
        logger.info(f"{crypto_type} deposit made: User {chat_id}, Amount {amount} {crypto_type}, Previous balance ${previous_balance:.2f}, New balance ${updated_balance:.2f}")
        
        register_audit(chat_id, f"{crypto_type}_deposit", usd_amount, previous_balance, updated_balance)
    else:
        bot.send_message(chat_id, "An error occurred while processing the deposit. Please try again.", reply_markup=generate_initial_markup())
        logger.error(f"Failed to process {crypto_type} deposit: User {chat_id}, Amount {amount} {crypto_type}")

def show_history(message):
    if not db_available:
        bot.send_message(message.chat.id, "Oops, our database is experiencing instability. Please contact support.")
        return

    chat_id = message.chat.id
    records = audit.find({'chat_id': chat_id}).sort('timestamp', -1).limit(10)  # Limit to last 10 transactions
    
    if records.count() == 0:
        bot.send_message(chat_id, "No transaction history found.", reply_markup=generate_initial_markup())
        return

    history = "Your recent transaction history:\n\n"
    for record in records:
        history += (f"Type: {record['operation_type']}, Amount: ${record['amount']:.2f}, "
                    f"Balance after: ${record['current_balance']:.2f}, "
                    f"Date: {record['timestamp'].strftime('%d/%m/%Y %H:%M:%S')}\n\n")
    
    bot.send_message(chat_id, history, reply_markup=generate_initial_markup())
    logger.info(f"Transaction history requested by user: {chat_id}")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, "I'm sorry, I didn't understand that command. Please use the buttons below or type /start to see available options.", reply_markup=generate_initial_markup())

if __name__ == '__main__':
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Python path: {sys.executable}")
    logger.info("Bot started. Press Ctrl+C to stop.")
    bot.polling(none_stop=True)