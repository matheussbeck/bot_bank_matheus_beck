- **User Registration**: Automatically registers new users when they interact with the bot for the first time, initializing their account with a balance of zero.

- **Balance Inquiry**: Users can check their current account balance. If any transactions have been made, details about the last transaction are provided.

- **Deposit**: Allows users to deposit a specified amount into their account. The bot confirms the deposit amount before completing the transaction, and updates the user’s balance.

- **Withdrawal**: Users can request to withdraw funds from their account. The bot ensures that there are sufficient funds before processing the withdrawal, and confirms the transaction.

- **Transaction History**: Displays the last 10 transactions made by the user, including the operation type (deposit or withdrawal), the amount, and timestamps for each transaction.

- **Audit Logging**: All transactions (deposits and withdrawals) are recorded in a MongoDB database, tracking the operation type, the amount, previous and updated balances, and the time of the transaction.

- **Database Connection and Error Handling**: The bot connects to a MongoDB database to store user data and transactions. It includes error handling for connection issues and informs users if the database is unavailable.


🚀 Desenvolvi e implementei um Bot Bancário automatizado no Telegram, hospedado na Nuvem Oracle (Ubuntu), utilizando as melhores práticas em desenvolvimento full-stack com Python e MongoDB. Este projeto inovador foi criado para facilitar a gestão de contas bancárias diretamente pelo Telegram, com uma arquitetura eficiente e segura.

Funcionalidades principais:
Registro de Usuários Automático: O bot detecta novos usuários e os registra automaticamente, inicializando suas contas com um saldo zero, proporcionando uma experiência simplificada de onboarding.

Consulta de Saldo: Permite que os usuários consultem o saldo atual da conta. Caso existam transações, os detalhes da última operação são exibidos, tornando as consultas mais transparentes e informativas.

Depósitos: Usuários podem depositar fundos, com confirmação de valor antes da conclusão da operação. O saldo é atualizado em tempo real, com logs detalhados.

Saques: O bot verifica se há saldo suficiente antes de autorizar saques, garantindo segurança e transparência no processo de retirada de fundos.

Histórico de Transações: Exibe as 10 últimas transações realizadas, incluindo tipo de operação (depósito ou saque), valor, saldo anterior e atual, além de carimbo de tempo detalhado para cada movimentação.

Registro de Auditoria: Todas as operações (depósitos e saques) são armazenadas em uma base de dados MongoDB, incluindo informações completas sobre cada transação (tipo, valor, saldo anterior e atual, data e hora), assegurando total controle e rastreabilidade.

Conexão com Banco de Dados e Tratamento de Erros: O bot se conecta a um banco de dados MongoDB para gerenciar os dados dos usuários e transações. Ele inclui manipulação de erros robusta, notificando os usuários em caso de instabilidade na conexão com o banco de dados, garantindo uma experiência de uso confiável.

Tecnologias e Ferramentas:
💻 Stack: Python, MongoDB, Docker, Oracle Cloud, Ubuntu
📡 APIs: Telegram Bot API
🔐 Segurança: Registros detalhados de auditoria e tratamento de erros
📊 Escalabilidade e Monitoramento: Logs detalhados com o módulo logging para rastreamento de operações críticas

Palavras-chave:
Python, Full-Stack Development, MongoDB, Telegram Bot, Cloud Computing, Oracle Cloud, APIs, NoSQL Databases, Automation, Auditing, Error Handling, Logging, Ubuntu, DevOps, Financial Services, RPA, Database Management
