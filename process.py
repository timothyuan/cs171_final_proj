import queue
import random
import socket
import sys
import threading
import time
from hashlib import sha256
import os



# PID of the process
PID = sys.argv[1]

# IP address of the process
IP = '127.0.0.1'

# Dictionary containing all ports of all processes
# Used for UDP connection
PORTS = {
    "p1": 3001, 
    "p2": 3002, 
    "p3": 3003, 
    "p4": 3004, 
    "p5": 3005
}

# Dictionary containing the state of each connection
# Address: Connection state (bool)
CONN_STATE = {
    (IP, 3001): True,
    (IP, 3002): True,
    (IP, 3003): True,
    (IP, 3004): True,
    (IP, 3005): True
}

# For testing purposes
addr_to_PID = {
    (IP, 3001): 'p1',
    (IP, 3002): 'p2',
    (IP, 3003): 'p3',
    (IP, 3004): 'p4',
    (IP, 3005): 'p5'
}

# Amount of money in the bank
balance = 100

# List of blocks
# block - list [txns, nonce, hash]
# txns - list of tuples (sender, receiver, amount) converted to a string
blockchain = []

# List of transactions to be added to pending
# transactions - tuple (sender, receiver, amount)
# Used to ensure that transfers added during paxos are not lost
transfers = []

# List of transactions to be added to the blockchain 
# transactions - tuple (sender, receiver, amount)
pending = []

# List of promises from other processes
# promise - list [promise, BallotNum, ID, AcceptNum, ID, AcceptVal]
promised = []

# Number of accepted messages from other processes
accepted = 0

# Ballot that the process gives its promise to
# format - (BallotNum, PID)
ballotNum = (0, PID, 0)

# Ballot number associated with acceptVal
# format - (BallotNum, PID)
acceptNum = (0, '', 0)

# Proposed block converted into string
# format - txns||nonce||hash
acceptVal = 'NULL'

# Queue that holds all events of the process
# Possible events: ['transfer', 'balance', 'blockchain', 'fail link', 'fix']
events = queue.Queue()

# Create socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind((IP, PORTS[PID]))

# Lock to ensure mutual exclusion
lock = threading.Lock()

def message(msg,addr):
    # Fixed delay for each message
    time.sleep(2)
    # Check if connection is valid
    if CONN_STATE[addr]:
        s.sendto(msg.encode(),addr)

# Thread for receiving all messages
def comm():
    global accepted
    global acceptNum
    global acceptVal
    global balance
    global ballotNum
    global blockchain
    global events
    global promised
    global pending

    while True:
        msg, addr = s.recvfrom(1024)
        msg = msg.decode().split('/')

        # Message type, one of the following:
        # prepare, promise, accept, accepted, decide
        type = msg[0]

        with lock:
            # Pretend message was never received if connection is broken
            if CONN_STATE[addr] == False:
                continue
            # prepare/BallotNum/ID/Depth
            if type == 'prepare':
                # Send updated blockchain back to sender if sender's depth is shorter
                if int(msg[3]) < len(blockchain):
                    for i in range(int(msg[3]), len(blockchain)):
                        block = blockchain[i]
                        update = block[0] + '||' + block[1] + '||' + block[2]
                        update = 'update/' + update + '/' + str(i)
                        threading.Thread(target = message, args = (update, addr)).start()
                    continue
                # Ask sender for updated blockchain if own blockchain is shorter
                elif int(msg[3]) > len(blockchain):
                    threading.Thread(target = message, args = ('request/' + str(len(blockchain)), addr)).start()
                    continue
                b = (int(msg[1]),msg[2],int(msg[3]))
                # TESTING: Print receive 
                print('Received PREPARE for ballot ' + str(b))
                # Check if the received ballot is larger than the promised ballot
                # If so, update ballotNum, send 'promise' back to sender
                if b >= ballotNum:
                    ballotNum = b
                    response = ('promise/' + str(ballotNum[0]) + '/' + ballotNum[1] + '/' + str(ballotNum[2]) + '/' +
                               str(acceptNum[0]) + '/' + acceptNum[1] + '/' + str(acceptNum[2]) + '/' + str(acceptVal) )
                    threading.Thread(target = message, args = (response, addr)).start()
                    # TESTING: Print sending response
                    print('Sending PROMISE for ballot ' + str(b))
            # promise/BallotNum/ID/Depth/AcceptNum/ID/Depth/AcceptVal
            elif type == 'promise':
                # Only accept promises if the ballotNum matches
                if (int(msg[1]), msg[2], int(msg[3])) != ballotNum:
                    continue
                # Add promise into list of promises
                promised.append(msg)
                # TESTING: Print received promise
                print('Received PROMISE for ballot ' + str(ballotNum))
            # accept/BallotNum/ID/Depth/Value
            elif type == 'accept':
                # Ignore messages for shorter blockchains
                if int(msg[3]) < len(blockchain):
                    continue
                # Ask sender for updated blockchain if own blockchain is shorter
                elif int(msg[3]) > len(blockchain):
                    threading.Thread(target = message, args = ('request/' + str(len(blockchain)), addr)).start()
                    continue
                b = (int(msg[1]),msg[2],int(msg[3]))
                # TESTING: Print receive 
                print('Received ACCEPT for ballot ' + str(b))
                # Check if the received ballot is larger than the promised ballot
                # If so, update acceptNum and acceptVal, send 'accepted' back to sender
                if b >= ballotNum:
                    acceptNum = b
                    acceptVal = msg[4]
                    response = 'accepted/' + str(acceptNum[0]) + '/' + acceptNum[1] + '/' + str(acceptNum[2]) + '/' + str(acceptVal)
                    threading.Thread(target = message, args = (response, addr)).start()
                    # TESTING: Print sending response
                    print('Sending ACCEPTED for ballot ' + str(b))
            # accepted/BallotNum/ID/Depth/Value
            elif type == 'accepted':
                # Ignore messages for shorter blockchains
                if int(msg[3]) != len(blockchain):
                    continue
                # Increment number of 'accepted' messages by 1
                accepted += 1
                # TESTING: Print received accepted
                print('Received ACCEPTED for ballot ' + str(ballotNum))
            # decide/acceptVal/Depth
            elif type == 'decide':
                # Ignore messages for shorter blockchains
                if int(msg[2]) < len(blockchain):
                    continue
                # Ask sender for updated blockchain if own blockchain is shorter
                elif int(msg[2]) > len(blockchain):
                    threading.Thread(target = message, args = ('request/' + str(len(blockchain)), addr)).start()
                    continue
                # TESTING: Print received decision
                print('Received DECIDE from ' + addr_to_PID[addr] + ', adding block to blockchain')
                # Update local blockchain
                acceptVal = msg[1]
                # TESTING: print acceptVal
                print(acceptVal)
                blockchain.append(acceptVal.split('||'))
                # Update balance
                update = acceptVal.split('||')[0]
                update = update[1:-1]
                for char in ')(\'':
                    update = update.replace(char,'')
                update = update.split(', ')
                txns = []
                for i in range(len(update)//3):
                    txns.append((update[3*i], update[3*i+1], update[3*i+2]))
                for t in txns:
                    if t[0] == PID:
                        balance -= int(t[2])
                        pending = []
                    if t[1] == PID:
                        balance += int(t[2])
                # Reset all paxos variables for the new round of paxos
                promised = []
                accepted = 0
                ballotNum = (0, PID, 0)
                acceptNum = (0, '', 0)
                acceptVal = 'NULL'
            # request/depth
            elif type == 'request':
                # Check if own blockchain is long enough to respond to the request
                if int(msg[1]) >= len(blockchain):
                    continue
                # Send all blocks that the sender is missing
                for i in range(int(msg[1]), len(blockchain)):
                    block = blockchain[i]
                    update = block[0] + '||' + block[1] + '||' + block[2]
                    update = 'update/' + update + '/' + str(i)
                    time.sleep(0.01)
                    threading.Thread(target = message, args = (update, addr)).start()
            # update/acceptVal/depth
            elif type == 'update':
                # Check if given block is the next block needed
                if int(msg[2]) != len(blockchain):
                    continue
                blockchain.append(msg[1].split('||'))
                # Update balance
                update = msg[1].split('||')[0]
                update = update[1:-1]
                for char in ')(\'':
                    update = update.replace(char,'')
                update = update.split(', ')
                txns = []
                for i in range(len(update)//3):
                    txns.append((update[3*i], update[3*i+1], update[3*i+2]))
                for t in txns:
                    if t[0] == PID:
                        balance -= int(t[2])
                        pending = []
                    if t[1] == PID:
                        balance += int(t[2])


# Thread for processesing events given by the command line             
def process():
    global CONN_STATE
    global events
    global transfers

    while True:
        e = events.get()
        type = event[0]
        with lock:
            if type == 'balance':
                print('BALANCE: ' + str(balance))
            elif type == 'blockchain':
                for i in range(len(blockchain)):
                    block = blockchain[i]
                    print('------------------------------ BLOCK ' + str(i+1) + ' ------------------------------')
                    print('txns: ' + block[0])
                    print('nonce: ' + block[1])
                    print('hash: ' + block[2])
                print('------------------------- END OF BLOCKCHAIN -------------------------')
            # fail link, DEST
            elif type == 'fail link':
                CONN_STATE[(IP, PORTS[e[1]])] = False
            # fail link, DEST
            elif type == 'fix link':
                CONN_STATE[(IP, PORTS[e[1]])] = True
            # transfer, receiver, amount
            elif type == 'transfer':
                temp = balance
                for t in transfers:
                    temp -= int(t[2])
                for p in pending:
                    temp -= int(p[2])
                # Make sure there is sufficient money for the transfer
                if temp <= int(e[2]):
                    print('Insufficient balance for: ' + str(e))
                    print('Transfer FAILED')
                    continue
                # Append transfer to list of transfers
                transfers.append((PID,e[1],e[2]))
            elif type == 'fail process':
                f = open(PID + '.txt', 'w')
                # pending, transfer
                for i in pending:
                    f.write(str(i) + '\n')
                for j in transfers:
                    f.write(str(j) + '\n')
                f.close()
                os._exit(0)
            # print all transactions in queue
            elif type == 'queue':
                print('Pending Transactions:')
                for i in pending:
                    print(i)
                for j in transfers:
                    print(j)


# Thread to run paxos
def paxos():
    global accepted
    global acceptNum
    global acceptVal
    global balance
    global ballotNum
    global blockchain
    global events
    global promised
    global transfers
    global PID
    global pending
    while True:
        # Do nothing if no transactions
        with lock:
            if len(transfers) == 0 and len(pending) == 0 and acceptVal == 'NULL':
                continue
        # Sleep to allow for multiple transactions in a block
        time.sleep(7)
        # PHASE I: LEADER ELECTION
        while True:
            # Add all transactions in transfer to pending
            # Ensures that transfers added by user while paxos is running are not lost
            with lock:
                for t in transfers:
                    pending.append(t)
                transfers = []
            # If pending is cleared, break out to the outer loop and wait for transactions
            with lock:
                if len(pending) == 0 and acceptVal == 'NULL':
                    break
            # Random wait before start of paxos
            time.sleep(random.randint(0,5))
            with lock:
                promised = []
                accepted = 0
                ballotNum = (ballotNum[0] + 1, PID, len(blockchain))
                # prepare/BallotNum/ID/Depth 
                prepare = 'prepare/' + str(ballotNum[0]) + '/' + ballotNum[1] + '/' + str(ballotNum[2])
                # send prepare messages to all processes
                for conn in PORTS:
                    if conn != PID:
                        addr = (IP, PORTS[conn])
                        threading.Thread(target = message, args = (prepare, addr)).start()
            # Wait for 'promise' reponses
            # Acts as a psuedo timeout
            time.sleep(4.5)
            with lock:
                # If not enough promises, start from PHASE I again
                if len(promised) < 2:
                    continue
            with lock:
                # If all acceptVal from promises are empty, set own acceptVal
                if all(p[-1] == 'NULL' for p in promised):
                    prevHash = ''
                    if len(blockchain) != 0:
                        prevHash = blockchain[-1][0] + '||' + blockchain[-1][1] + '||' + blockchain[-1][2]
                    prevHash = sha256(prevHash.encode('utf-8')).hexdigest()
                    # Find appropriate nonce
                    # h = sha256(txns||nonce||hash) must end with a number from 0-4
                    while True:
                        nonce = str(random.randint(0, 100))
                        acceptVal = str(pending) + "||" + nonce + "||" + prevHash
                        h = sha256(acceptVal.encode('utf-8')).hexdigest()
                        if '0' <= h[-1] <= '4':
                            # TESTING: Print nonce and hash value
                            print('Nonce: ' + nonce)
                            print('Hash value: ' + h)
                            break
                # If acceptVal are not all empty, promote the acceptVal with the highest ballotNum
                else:
                    promised.sort(reverse = True)
                    acceptVal = promised[0][-1]
            # PHASE II: CONSENSUS
            with lock:
                # accept/BallotNum/ID/Depth/Value
                accept = 'accept/' + str(ballotNum[0]) + '/' + ballotNum[1] + '/' + str(ballotNum[2]) + '/' + acceptVal
                # Send 'accept' messages to all processes
                for conn in PORTS:
                    if conn != PID:
                        addr = (IP, PORTS[conn])
                        threading.Thread(target = message, args = (accept, addr)).start()
            # Wait for 'promise' reponses
            # Acts as a psuedo timeout
            time.sleep(4.5)
            with lock:
                # If the process does not receive the majority of 'accepted', restart from PHASE I
                if accepted < 2:
                    continue
            # PHASE III: Decide
            with lock:
                # Send 'decide' message to all processes
                decide = 'decide/' + acceptVal + '/' + str(ballotNum[2])
                #testing: sending decide
                print('SENDING DECIDE TO ALL PROCESSES')
                print(acceptVal)
                for conn in PORTS:
                    if conn != PID:
                        addr = (IP, PORTS[conn])
                        threading.Thread(target = message, args = (decide, addr)).start()
                # Add block to blockchain
                blockchain.append(acceptVal.split('||'))
                # Update balance
                update = acceptVal.split('||')[0]
                update = update[1:-1]
                for char in ')(\'':
                    update = update.replace(char,'')
                update = update.split(', ')
                txns = []
                for i in range(len(update)//3):
                    txns.append((update[3*i], update[3*i+1], update[3*i+2]))
                for t in txns:
                    if t[0] == PID:
                        balance -= int(t[2])
                        pending = []
                    if t[1] == PID:
                        balance += int(t[2])
                # clear_buffer()
                # time.sleep(7)
                # Reset all paxos variables for the new round of paxos
                promised = []
                accepted = 0
                ballotNum = (0, PID, 0)
                acceptNum = (0, '', 0)
                acceptVal = 'NULL'
                break       

# update to saved version
with lock:
    if len(sys.argv) == 3:
        file_name = sys.argv[2]
        save_file = open(file_name, 'r')
        for line in save_file:
            line = line[1:-1]
            line = line.replace("\'",'')
            line = line.split(', ')
            pending.append((line[0], line[1], line[2]))
        # Ask for blockchain from other processes
        for conn in PORTS:
            if conn != PID:
                addr = (IP, PORTS[conn])
                threading.Thread(target = message, args = ('request/0', addr)).start()
                time.sleep(0.1)

# Start threads
threading.Thread(target = process).start()
threading.Thread(target = comm).start()
threading.Thread(target = paxos).start()

# Continuously take input from command line
while True:
    event = input()
    event = event.split(', ')
    # Place event in queue if valid
    with lock:
        if event[0] in ['transfer', 'balance', 'blockchain', 'fail link', 'fix link', 'fail process', 'queue']:
            events.put(event)
        else:
            print('Invalid Command')