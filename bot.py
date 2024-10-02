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
users = None
audit = None

def connect_mongodb():
    global db_available, users, audit
    try:
        client = MongoClient(MONGO_URI)
        client.admin.command('ismaster')
        logger.info("Successful connection to local MongoDB")
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
        logger.error("Failed to connect to local MongoDB. Check if the MongoDB service is running.")
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
        ("History", "history")
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
            'last_transaction': None
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
    elif call.data.startswith("confirm_deposit_"):
        amount = float(call.data.split("_")[2])
        confirm_deposit(call.message, amount)
    elif call.data.startswith("confirm_withdraw_"):
        amount = float(call.data.split("_")[2])
        confirm_withdrawal(call.message, amount)
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
    user = users.find_one({'_id': chat_id})
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
        user = users.find_one({'_id': chat_id})
        current_balance = user['balance']
        
        buttons = [
            ("Confirm", f"confirm_deposit_{amount}"),
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
        
        # Register in audit
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
            ("Confirm", f"confirm_withdraw_{amount}"),
            ("Cancel", "cancel_operation")
        ]
        markup = generate_markup(buttons)
        bot.send_message(chat_id, f"You want to withdraw ${amount:.2f}. Your current balance is ${current_balance:.2f}. After withdrawal, your balance will be ${current_balance - amount:.2f}. Confirm?", reply_markup=markup)
    except ValueError as e:
        bot.send_message(message.chat.id, f"Invalid amount. Please try again.")
        bot.register_next_step_handler(message, process_withdrawal_amount)

def confirm_withdrawal(message, amount):
    chat_id = message.chat.id
    timestamp = datetime.now()
    
    user = users.find_one({'_id': chat_id})
    previous_balance = user['balance']
    
    if previous_balance < amount:
        bot.send_message(chat_id, f"Insufficient balance for withdrawal. Your current balance is ${previous_balance:.2f}.", reply_markup=generate_initial_markup())
        logger.warning(f"Withdrawal attempt with insufficient balance: User {chat_id}, Amount ${amount:.2f}, Current balance ${previous_balance:.2f}")
        return
    
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
        
        # Register in audit
        register_audit(chat_id, "withdrawal", amount, previous_balance, updated_balance)
    else:
        bot.send_message(chat_id, "An error occurred while processing the withdrawal. Please try again.", reply_markup=generate_initial_markup())
        logger.error(f"Failed to process withdrawal: User {chat_id}, Amount ${amount:.2f}")

def show_history(message):
    chat_id = message.chat.id
    history = audit.find({'chat_id': chat_id}).sort('timestamp', -1).limit(10)  # Last 10 transactions
    
    if audit.count_documents({'chat_id': chat_id}) == 0:
        bot.send_message(chat_id, "You don't have any transaction history yet.", reply_markup=generate_initial_markup())
        return
    
    response = "Transaction history (last 10):\n\n"
    for transaction in history:
        response += f"{transaction['timestamp'].strftime('%d/%m/%Y %H:%M:%S')} - {transaction['operation_type'].capitalize()} of ${transaction['amount']:.2f}\n"
        response += f"Previous balance: ${transaction['previous_balance']:.2f} | Current balance: ${transaction['current_balance']:.2f}\n\n"
    
    bot.send_message(chat_id, response, reply_markup=generate_initial_markup())

if __name__ == '__main__':
    logger.info("Bot started. Press Ctrl+C to stop.")
    bot.polling(none_stop=True)