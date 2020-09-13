#!/usr/bin/env python

import socket, random, time, json, os

# HOST = "127.0.0.1"
# PORT = 9010
# HOST = "52.190.28.214"
HOST = "52.224.82.132"
PORT = 44500

movement = ['movenorth', 'movesouth', 'moveeast', 'movewest']

run = True

# sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# if 'PAL_PORT' in os.environ:
#     sock.connect((HOST, int(os.environ['PAL_PORT'])))
#     print('Using Port: ' + os.environ['PAL_PORT'])
# else:
print('Using Port: ' + str(PORT))

while run:  # main loop
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    # sock.connect((HOST, PORT))
    userInput = input()
    if userInput == 'exit':  # wait for user input commands
        run = False
    elif userInput == 'wonder':  # testing automatic commands
        count = 200
        while count > 0:
            sock.send(bytes(random.choice(movement), 'utf-8'))
            sock.close()  # socket must be closed between after command
            time.sleep(0.5)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((HOST, PORT))
            count = count - 1
    else:
        sock.send(str.encode(userInput + '\n'))


    # Look for the response
    amount_received = 0
    amount_expected = 16
    # if userInput.startswith('DATA') or userInput.startswith('LL'):	 # if we need to receive something, we have to listen for it. Maybe this should be a separate thread?
    # 	data = ''
    # 	data = sock.recv(10240).decode()
    # 	data_dict = json.loads(data)
    # 	print (data_dict)
    # if not userInput.startswith('START'):
    if True:
        BUFF_SIZE = 4096  # 4 KiB
        data = b''
        while True:
            part = sock.recv(BUFF_SIZE)
            data += part
            if len(part) < BUFF_SIZE:
                # either 0 or end of data
                break
        print(data)
    sock.close()
    # data_dict = json.loads(data)
    # print(data_dict)
sock.close()

print("Socket closed")
