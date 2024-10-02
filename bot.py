import sys
print(f"Python version: {sys.version}")
print(f"Python path: {sys.executable}")

from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from datetime import datetime
import logging

# Configuração do logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuração do bot
TOKEN = "7191121650:AAGDXIJRPyAVqXA99t6pWK0wvsbJYRN6jyo"
bot = TeleBot(TOKEN)

# Configuração do MongoDB
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "banco_telegram"

# Variáveis globais para controlar o estado da conexão com o banco de dados
db_disponivel = False
usuarios = None
auditoria = None

def conectar_mongodb():
    global db_disponivel, usuarios, auditoria
    try:
        client = MongoClient(MONGO_URI)
        client.admin.command('ismaster')
        logger.info("Conexão bem-sucedida com o MongoDB local")
        db = client[DB_NAME]
        
        if 'usuarios' not in db.list_collection_names():
            db.create_collection('usuarios')
            logger.info("Coleção 'usuarios' criada com sucesso.")
        usuarios = db['usuarios']
        
        if 'auditoria' not in db.list_collection_names():
            db.create_collection('auditoria')
            logger.info("Coleção 'auditoria' criada com sucesso.")
        auditoria = db['auditoria']
        
        db_disponivel = True
        return client, db
    except ConnectionFailure:
        logger.error("Falha ao conectar ao MongoDB local. Verifique se o serviço MongoDB está rodando.")
        db_disponivel = False
        return None, None

# Estabelece a conexão com o MongoDB
client, db = conectar_mongodb()

def registrar_auditoria(chat_id, tipo_operacao, valor, saldo_anterior, saldo_atual):
    if not db_disponivel:
        logger.error("Falha ao registrar auditoria: banco de dados indisponível")
        return
    
    registro = {
        'chat_id': chat_id,
        'tipo_operacao': tipo_operacao,
        'valor': valor,
        'saldo_anterior': saldo_anterior,
        'saldo_atual': saldo_atual,
        'timestamp': datetime.now()
    }
    
    try:
        auditoria.insert_one(registro)
        logger.info(f"Registro de auditoria criado: {registro}")
    except Exception as e:
        logger.error(f"Erro ao criar registro de auditoria: {e}")

def gerar_markup(botoes):
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    for texto, callback_data in botoes:
        markup.add(InlineKeyboardButton(texto, callback_data=callback_data))
    return markup

def gerar_markup_inicial():
    botoes = [
        ("Verificar Saldo", "verificar_saldo"),
        ("Depositar", "depositar"),
        ("Sacar", "sacar"),
        ("Histórico", "historico")
    ]
    return gerar_markup(botoes)

@bot.message_handler(commands=['start'])
def handle_start(message):
    if not db_disponivel:
        bot.reply_to(message, "Ops, nosso banco de dados apresentou instabilidades. Por favor, entre em contato com o suporte.")
        return

    chat_id = message.chat.id
    user = usuarios.find_one({'_id': chat_id})
    if not user:
        usuarios.insert_one({
            '_id': chat_id,
            'saldo': 0,
            'ultima_transacao': None
        })
        logger.info(f"Novo usuário registrado: {chat_id}")
    bot.reply_to(message, "Bem-vindo ao Bot Bancário! O que você gostaria de fazer?", reply_markup=gerar_markup_inicial())

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if not db_disponivel:
        bot.answer_callback_query(call.id, "Desculpe, o serviço está temporariamente indisponível. Por favor, tente novamente mais tarde.")
        return

    chat_id = call.message.chat.id
    if call.data == "verificar_saldo":
        verificar_saldo(call.message)
    elif call.data == "depositar":
        iniciar_deposito(call.message)
    elif call.data == "sacar":
        iniciar_saque(call.message)
    elif call.data.startswith("confirmar_deposito_"):
        valor = float(call.data.split("_")[2])
        confirmar_deposito(call.message, valor)
    elif call.data.startswith("confirmar_saque_"):
        valor = float(call.data.split("_")[2])
        confirmar_saque(call.message, valor)
    elif call.data == "cancelar_operacao":
        bot.send_message(chat_id, "Operação cancelada.", reply_markup=gerar_markup_inicial())
        logger.info(f"Operação cancelada pelo usuário: {chat_id}")
    elif call.data == "historico":
        mostrar_historico(call.message)

def verificar_saldo(message):
    if not db_disponivel:
        bot.send_message(message.chat.id, "Ops, nosso banco de dados apresentou instabilidades. Por favor, entre em contato com o suporte.")
        return

    chat_id = message.chat.id
    user = usuarios.find_one({'_id': chat_id})
    if user:
        saldo = user['saldo']
        ultima_transacao = user['ultima_transacao']
        if ultima_transacao:
            resposta = f"Seu saldo atual é: R${saldo:.2f}\n\nÚltima transação: {ultima_transacao['tipo']} de R${ultima_transacao['valor']:.2f} em {ultima_transacao['data']}"
        else:
            resposta = f"Seu saldo atual é: R${saldo:.2f}\n\nVocê ainda não realizou nenhuma transação."
    else:
        resposta = "Desculpe, não foi possível encontrar suas informações. Por favor, tente novamente mais tarde."
    
    bot.send_message(chat_id, resposta, reply_markup=gerar_markup_inicial())
    logger.info(f"Saldo verificado para o usuário: {chat_id}")

def iniciar_deposito(message):
    if not db_disponivel:
        bot.send_message(message.chat.id, "Ops, nosso banco de dados apresentou instabilidades. Por favor, entre em contato com o suporte.")
        return

    bot.send_message(message.chat.id, "Por favor, digite o valor que deseja depositar:")
    bot.register_next_step_handler(message, processar_valor_deposito)

def processar_valor_deposito(message):
    try:
        valor = float(message.text)
        if valor <= 0:
            raise ValueError("O valor deve ser maior que zero.")
        
        chat_id = message.chat.id
        user = usuarios.find_one({'_id': chat_id})
        saldo_atual = user['saldo']
        
        botoes = [
            ("Confirmar", f"confirmar_deposito_{valor}"),
            ("Cancelar", "cancelar_operacao")
        ]
        markup = gerar_markup(botoes)
        bot.send_message(chat_id, f"Você deseja depositar R${valor:.2f}. Seu saldo atual é R${saldo_atual:.2f}. Confirma?", reply_markup=markup)
    except ValueError as e:
        bot.send_message(message.chat.id, f"Valor inválido. Por favor, tente novamente.")
        bot.register_next_step_handler(message, processar_valor_deposito)

def confirmar_deposito(message, valor):
    chat_id = message.chat.id
    timestamp = datetime.now()
    
    user = usuarios.find_one({'_id': chat_id})
    saldo_anterior = user['saldo']
    
    resultado = usuarios.update_one(
        {'_id': chat_id},
        {
            '$inc': {'saldo': valor},
            '$set': {
                'ultima_transacao': {
                    'tipo': 'depósito',
                    'valor': valor,
                    'data': timestamp.strftime("%d/%m/%Y %H:%M:%S")
                }
            }
        }
    )
    
    if resultado.modified_count > 0:
        saldo_atualizado = saldo_anterior + valor
        resposta = (f"Depósito de R${valor:.2f} realizado com sucesso!\n"
                    f"Saldo anterior: R${saldo_anterior:.2f}\n"
                    f"Saldo atualizado: R${saldo_atualizado:.2f}\n"
                    f"Data e hora da transação: {timestamp.strftime('%d/%m/%Y %H:%M:%S')}")
        bot.send_message(chat_id, resposta, reply_markup=gerar_markup_inicial())
        logger.info(f"Depósito realizado: Usuário {chat_id}, Valor R${valor:.2f}, Saldo anterior R${saldo_anterior:.2f}, Novo saldo R${saldo_atualizado:.2f}")
        
        # Registrar na auditoria
        registrar_auditoria(chat_id, "depósito", valor, saldo_anterior, saldo_atualizado)
    else:
        bot.send_message(chat_id, "Ocorreu um erro ao processar o depósito. Por favor, tente novamente.", reply_markup=gerar_markup_inicial())
        logger.error(f"Falha ao processar depósito: Usuário {chat_id}, Valor R${valor:.2f}")

def iniciar_saque(message):
    if not db_disponivel:
        bot.send_message(message.chat.id, "Ops, nosso banco de dados apresentou instabilidades. Por favor, entre em contato com o suporte.")
        return

    chat_id = message.chat.id
    user = usuarios.find_one({'_id': chat_id})
    saldo_atual = user['saldo']

    bot.send_message(chat_id, f"Seu saldo atual é R${saldo_atual:.2f}. Por favor, digite o valor que deseja sacar:")
    bot.register_next_step_handler(message, processar_valor_saque)

def processar_valor_saque(message):
    try:
        valor = float(message.text)
        if valor <= 0:
            raise ValueError("O valor deve ser maior que zero.")
        
        chat_id = message.chat.id
        user = usuarios.find_one({'_id': chat_id})
        saldo_atual = user['saldo']
        
        if saldo_atual < valor:
            bot.send_message(chat_id, f"Saldo insuficiente. Seu saldo atual é R${saldo_atual:.2f}. Por favor, digite um novo valor para saque:")
            bot.register_next_step_handler(message, processar_valor_saque)
            return
        
        botoes = [
            ("Confirmar", f"confirmar_saque_{valor}"),
            ("Cancelar", "cancelar_operacao")
        ]
        markup = gerar_markup(botoes)
        bot.send_message(chat_id, f"Você deseja sacar R${valor:.2f}. Seu saldo atual é R${saldo_atual:.2f}. Após o saque, seu saldo será R${saldo_atual - valor:.2f}. Confirma?", reply_markup=markup)
    except ValueError as e:
        bot.send_message(message.chat.id, f"Valor inválido. Por favor, tente novamente.")
        bot.register_next_step_handler(message, processar_valor_saque)

def confirmar_saque(message, valor):
    chat_id = message.chat.id
    timestamp = datetime.now()
    
    user = usuarios.find_one({'_id': chat_id})
    saldo_anterior = user['saldo']
    
    if saldo_anterior < valor:
        bot.send_message(chat_id, f"Saldo insuficiente para realizar o saque. Seu saldo atual é R${saldo_anterior:.2f}.", reply_markup=gerar_markup_inicial())
        logger.warning(f"Tentativa de saque com saldo insuficiente: Usuário {chat_id}, Valor R${valor:.2f}, Saldo atual R${saldo_anterior:.2f}")
        return
    
    resultado = usuarios.update_one(
        {'_id': chat_id},
        {
            '$inc': {'saldo': -valor},
            '$set': {
                'ultima_transacao': {
                    'tipo': 'saque',
                    'valor': valor,
                    'data': timestamp.strftime("%d/%m/%Y %H:%M:%S")
                }
            }
        }
    )
    
    if resultado.modified_count > 0:
        saldo_atualizado = saldo_anterior - valor
        resposta = (f"Saque de R${valor:.2f} realizado com sucesso!\n"
                    f"Saldo anterior: R${saldo_anterior:.2f}\n"
                    f"Saldo atualizado: R${saldo_atualizado:.2f}\n"
                    f"Data e hora da transação: {timestamp.strftime('%d/%m/%Y %H:%M:%S')}")
        bot.send_message(chat_id, resposta, reply_markup=gerar_markup_inicial())
        logger.info(f"Saque realizado: Usuário {chat_id}, Valor R${valor:.2f}, Saldo anterior R${saldo_anterior:.2f}, Novo saldo R${saldo_atualizado:.2f}")
        
        # Registrar na auditoria
        registrar_auditoria(chat_id, "saque", valor, saldo_anterior, saldo_atualizado)
    else:
        bot.send_message(chat_id, "Ocorreu um erro ao processar o saque. Por favor, tente novamente.", reply_markup=gerar_markup_inicial())
        logger.error(f"Falha ao processar saque: Usuário {chat_id}, Valor R${valor:.2f}")

def mostrar_historico(message):
    chat_id = message.chat.id
    historico = auditoria.find({'chat_id': chat_id}).sort('timestamp', -1).limit(10)  # Últimas 10 transações
    
    if auditoria.count_documents({'chat_id': chat_id}) == 0:
        bot.send_message(chat_id, "Você ainda não possui histórico de transações.", reply_markup=gerar_markup_inicial())
        return
    
    resposta = "Histórico de transações (últimas 10):\n\n"
    for transacao in historico:
        resposta += f"{transacao['timestamp'].strftime('%d/%m/%Y %H:%M:%S')} - {transacao['tipo_operacao'].capitalize()} de R${transacao['valor']:.2f}\n"
        resposta += f"Saldo anterior: R${transacao['saldo_anterior']:.2f} | Saldo atual: R${transacao['saldo_atual']:.2f}\n\n"
    
    bot.send_message(chat_id, resposta, reply_markup=gerar_markup_inicial())

if __name__ == '__main__':
    logger.info("Bot iniciado. Pressione Ctrl+C para parar.")
    bot.polling(none_stop=True)