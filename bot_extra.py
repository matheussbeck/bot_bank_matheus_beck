import sys
print(f"Python version: {sys.version}")
print(f"Python path: {sys.executable}")

from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from datetime import datetime
import logging
import os
from dotenv import load_dotenv


load_dotenv()


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
bot = TeleBot(TOKEN)


MONGO_URI = os.getenv('MONGO_URI')
DB_NAME = os.getenv('DB_NAME')


db_available = False
users_extra = None
audit_extra = None

def connect_mongodb():
    global db_available, users_extra, audit_extra
    try:
        client = MongoClient(MONGO_URI)
        client.admin.command('ismaster')
        logger.info("Successful connection to local MongoDB")
        db = client[DB_NAME]
        
        if 'users_extra' not in db.list_collection_names():
            db.create_collection('users_extra')
            logger.info("Collection 'users_extra' created successfully.")
        users_extra = db['users_extra']
        
        if 'audit_extra' not in db.list_collection_names():
            db.create_collection('audit_extra')
            logger.info("Collection 'audit_extra' created successfully.")
        audit_extra = db['audit_extra']
        
        db_available = True
        return client, db
    except ConnectionFailure:
        logger.error("Failed to connect to local MongoDB. Check if the MongoDB service is running.")
        db_available = False
        return None, None


client, db = connect_mongodb()

def register_audit(chat_id, operation_type, amount, previous_balance, current_balance, method=None):
    if not db_available:
        logger.error("Failed to register audit: database unavailable")
        return
    
    record = {
        'chat_id': chat_id,
        'operation_type': operation_type,
        'amount': amount,
        'previous_balance': previous_balance,
        'current_balance': current_balance,
        'method': method,
        'timestamp': datetime.now()
    }
    
    try:
        audit_extra.insert_one(record)
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
        ("History", "history")
    ]
    return generate_markup(buttons)

@bot.message_handler(commands=['start'])
def handle_start(message):
    if not db_available:
        bot.reply_to(message, "Oops, our database is experiencing instability. Please contact support.")
        return

    chat_id = message.chat.id
    user = users_extra.find_one({'_id': chat_id})
    if not user:
        users_extra.insert_one({
            '_id': chat_id,
            'balance': 0,
            'last_transaction': None,
            'deposit_methods': [],
            'withdrawal_methods': []
        })
        logger.info(f"New user registered: {chat_id}")
    bot.reply_to(message, "Welcome to the Bank Bot! What would you like to do?", reply_markup=generate_initial_markup())

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if not db_available:
        bot.answer_callback_query(call.id, "Sorry, the service is temporarily unavailable. Please try again later.")
        return

    chat_id = call.message.chat.id
    if call.data == "check_balance":
        check_balance(call.message)
    elif call.data == "deposit":
        start_deposit(call.message)
    elif call.data == "withdraw":
        start_withdrawal(call.message)
    elif call.data.startswith("deposit_method_"):
        method_id = call.data.split("_")[2]
        process_deposit_method(call.message, method_id)
    elif call.data.startswith("withdrawal_method_"):
        method_id = call.data.split("_")[2]
        process_withdrawal_method(call.message, method_id)
    elif call.data.startswith("add_deposit_method_"):
        method_type = call.data.split("_")[3]
        add_deposit_method(call.message, method_type)
    elif call.data.startswith("add_withdrawal_method_"):
        method_type = call.data.split("_")[3]
        add_withdrawal_method(call.message, method_type)
    elif call.data.startswith("crypto_deposit_"):
        crypto_type = call.data.split("_")[2]
        process_crypto_deposit(call.message, crypto_type)
    elif call.data.startswith("crypto_withdrawal_"):
        crypto_type = call.data.split("_")[2]
        process_crypto_withdrawal(call.message, crypto_type)
    elif call.data.startswith("confirm_deposit_"):
        amount = float(call.data.split("_")[2])
        method_id = call.data.split("_")[3]
        confirm_deposit(call.message, amount, method_id)
    elif call.data.startswith("confirm_withdraw_"):
        amount = float(call.data.split("_")[2])
        method_id = call.data.split("_")[3]
        confirm_withdrawal(call.message, amount, method_id)
    elif call.data == "cancel_operation":
        bot.send_message(chat_id, "Operation cancelled.", reply_markup=generate_initial_markup())
        logger.info(f"Operation cancelled by user: {chat_id}")
    elif call.data == "history":
        show_history(call.message)

def check_balance(message):
    if not db_available:
        bot.send_message(message.chat.id, "Oops, our database is experiencing instability. Please contact support.")
        return

    chat_id = message.chat.id
    user = users_extra.find_one({'_id': chat_id})
    if user:
        balance = user['balance']
        last_transaction = user['last_transaction']
        if last_transaction:
            response = f"Your current balance is: ${balance:.2f}\n\nLast transaction: {last_transaction['type']} of ${last_transaction['amount']:.2f} on {last_transaction['date']}"
        else:
            response = f"Your current balance is: ${balance:.2f}\n\nYou haven't made any transactions yet."
    else:
        response = "Sorry, we couldn't find your information. Please try again later."
    
    bot.send_message(chat_id, response, reply_markup=generate_initial_markup())
    logger.info(f"Balance checked for user: {chat_id}")

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
        user = users_extra.find_one({'_id': chat_id})
        deposit_methods = user.get('deposit_methods', [])

        buttons = [
            (method['description'], f"deposit_method_{method['_id']}")
            for method in deposit_methods
        ]
        buttons.append(("Add New Method", "add_deposit_method"))
        buttons.append(("Cancel", "cancel_operation"))

        markup = generate_markup(buttons)
        bot.send_message(chat_id, f"You want to deposit ${amount:.2f}. Please select a deposit method:", reply_markup=markup)
    except ValueError as e:
        bot.send_message(message.chat.id, f"Invalid amount. Please try again.")
        bot.register_next_step_handler(message, process_deposit_amount)

def process_deposit_method(message, method_id):
    chat_id = message.chat.id
    user = users_extra.find_one({'_id': chat_id})
    deposit_methods = user.get('deposit_methods', [])
    selected_method = next((m for m in deposit_methods if str(m['_id']) == method_id), None)

    if selected_method:
        amount = float(message.text.split(" ")[-1].replace("$", ""))
        buttons = [
            ("Confirm", f"confirm_deposit_{amount}_{method_id}"),
            ("Cancel", "cancel_operation")
        ]
        markup = generate_markup(buttons)
        bot.send_message(chat_id, f"You selected {selected_method['description']} to deposit ${amount:.2f}. Confirm?", reply_markup=markup)
    else:
        bot.send_message(chat_id, "Invalid deposit method selected. Please try again.", reply_markup=generate_initial_markup())

def add_deposit_method(message):
    chat_id = message.chat.id
    buttons = [
        ("Bank Transfer", "add_deposit_method_bank"),
        ("Paypal", "add_deposit_method_paypal"),
        ("Crypto", "add_deposit_method_crypto"),
        ("Cancel", "cancel_operation")
    ]
    markup = generate_markup(buttons)
    bot.send_message(chat_id, "Please select the type of deposit method:", reply_markup=markup)

def add_withdrawal_method(message):
    chat_id = message.chat.id
    buttons = [
        ("Bank Transfer", "add_withdrawal_method_bank"),
        ("Paypal", "add_withdrawal_method_paypal"),
        ("Crypto", "add_withdrawal_method_crypto"),
        ("Cancel", "cancel_operation")
    ]
    markup = generate_markup(buttons)
    bot.send_message(chat_id, "Please select the type of withdrawal method:", reply_markup=markup)

def process_bank_deposit(message):
    chat_id = message.chat.id
    bank_name = message.text

    method = {
        'type': 'bank',
        'description': f"Bank Transfer - {bank_name}"
    }

    users_extra.update_one(
        {'_id': chat_id},
        {'$push': {'deposit_methods': method}}
    )

    bot.send_message(chat_id, f"Bank transfer method for {bank_name} added successfully.")
    start_deposit(message)

def process_paypal_deposit(message):
    chat_id = message.chat.id
    paypal_email = message.text

    method = {
        'type': 'paypal',
        'description': f"Paypal - {paypal_email}"
    }

    users_extra.update_one(
        {'_id': chat_id},
        {'$push': {'deposit_methods': method}}
    )

    bot.send_message(chat_id, f"Paypal method for {paypal_email} added successfully.")
    start_deposit(message)

def process_crypto_deposit(message, crypto_type):
    chat_id = message.chat.id
    crypto_address = message.text

    method = {
        'type': 'crypto',
        'description': f"Crypto - {crypto_type.upper()} - {crypto_address}"
    }

    users_extra.update_one(
        {'_id': chat_id},
        {'$push': {'deposit_methods': method}}
    )

    bot.send_message(chat_id, f"Crypto deposit method for {crypto_type.upper()} added successfully.")
    start_deposit(message)

def confirm_deposit(message, amount, method_id):
    chat_id = message.chat.id
    timestamp = datetime.now()
    
    user = users_extra.find_one({'_id': chat_id})
    previous_balance = user['balance']
    deposit_methods = user.get('deposit_methods', [])
    selected_method = next((m for m in deposit_methods if str(m['_id']) == method_id), None)

    if selected_method:
        result = users_extra.update_one(
            {'_id': chat_id},
            {
                '$inc': {'balance': amount},
                '$set': {
                    'last_transaction': {
                        'type': 'deposit',
                        'amount': amount,
                        'method': selected_method['description'],
                        'date': timestamp.strftime("%d/%m/%Y %H:%M:%S")
                    }
                }
            }
        )
        
        if result.modified_count > 0:
            updated_balance = previous_balance + amount
            response = (f"Deposit of ${amount:.2f} using {selected_method['description']} successful!\n"
                        f"Previous balance: ${previous_balance:.2f}\n"
                        f"Updated balance: ${updated_balance:.2f}\n"
                        f"Transaction date and time: {timestamp.strftime('%d/%m/%Y %H:%M:%S')}")
            bot.send_message(chat_id, response, reply_markup=generate_initial_markup())
            logger.info(f"Deposit made: User {chat_id}, Amount ${amount:.2f}, Method {selected_method['description']}, Previous balance ${previous_balance:.2f}, New balance ${updated_balance:.2f}")
            
            # Register in audit
            register_audit(chat_id, "deposit", amount, previous_balance, updated_balance, selected_method['description'])
        else:
            bot.send_message(chat_id, "An error occurred while processing the deposit. Please try again.", reply_markup=generate_initial_markup())
            logger.error(f"Failed to process deposit: User {chat_id}, Amount ${amount:.2f}, Method {selected_method['description']}")
    else:
        bot.send_message(chat_id, "Invalid deposit method selected. Please try again.", reply_markup=generate_initial_markup())
        logger.error(f"Invalid deposit method: User {chat_id}, Amount ${amount:.2f}, Method ID {method_id}")

def start_withdrawal(message):
    if not db_available:
        bot.send_message(message.chat.id, "Oops, our database is experiencing instability. Please contact support.")
        return

    chat_id = message.chat.id
    user = users_extra.find_one({'_id': chat_id})
    current_balance = user['balance']

    bot.send_message(chat_id, f"Your current balance is ${current_balance:.2f}. Please enter the amount you want to withdraw:")
    bot.register_next_step_handler(message, process_withdrawal_amount)

def process_withdrawal_amount(message):
    try:
        amount = float(message.text