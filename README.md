User Registration: Automatically registers new users when they interact with the bot for the first time, initializing their account with a balance of zero.
Balance Inquiry: Users can check their current account balance. If any transactions have been made, details about the last transaction are provided.
Deposit: Allows users to deposit a specified amount into their account. The bot confirms the deposit amount before completing the transaction, and updates the user’s balance.
Withdrawal: Users can request to withdraw funds from their account. The bot ensures that there are sufficient funds before processing the withdrawal, and confirms the transaction.
Transaction History: Displays the last 10 transactions made by the user, including the operation type (deposit or withdrawal), the amount, and timestamps for each transaction.
Audit Logging: All transactions (deposits and withdrawals) are recorded in a MongoDB database, tracking the operation type, the amount, previous and updated balances, and the time of the transaction.
Database Connection and Error Handling: The bot connects to a MongoDB database to store user data and transactions. It includes error handling for connection issues and informs users if the database is unavailable.
