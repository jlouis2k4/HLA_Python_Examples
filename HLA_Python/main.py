import subprocess
import threading
import time
import os
import signal
import queue
import json
from pyconstrobe import ProcessManager

FOM_PATH = "C:\\dev\\source\\constrobe\\Test.fed"
FEDERATION_NAME = "SimulationFederation"
#LISTENER_PATH = "C:\\dev\\tools\\certi\\ListenerFederate\\x64\\Release\\ListenerFederate.exe"
LISTENER_PATH = "C:\\dev\\tools\\certi\\ListenerFederate\\x64\\Debug\\ListenerFederate.exe"

shutdown_now = threading.Event()
events = queue.Queue()  

def send_control(p, line):
    try:
        if p.stdin:
            p.stdin.write(line + "\n")
            p.stdin.flush()
    except Exception:
        pass

def handle_new_line(line,proc):
    #print(f"[FROM C++] {line.strip()}")
    if "Queue3.CurCount:" in line:
        parts = line.split("Queue3.CurCount:")
        if len(parts) > 1:
            number_str = parts[1].strip().split()[0]
            count = int(number_str)
            #print("Queue3.CurCount =", count)
            if count>=5:
                message = "CONTROLSIGNAL SimA REMOVEFROMQUEUE Queue3 5\n"
                send_control(proc,message)
                message = "CONTROLSIGNAL SimB ADDTOQUEUE Queue2 5\n"
                send_control(proc,message)
    if "SimB.Queue.CurCount:" in line:
        parts = line.split("SimB.Queue.CurCount:")
        if len(parts) > 1:
            number_str = parts[1].strip().split()[0]
            count = int(number_str)
            if count > 40:
                print("TIME TO SHUT THIS DOWN")
                events.put(("shutdown", None))  
                shutdown_now.set()

def read_stdout(proc, callback, full_proc):
    for line in proc.stdout:
        if line:
            callback(line,proc)

def launch_listener():
    proc = subprocess.Popen(
        [LISTENER_PATH],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    thread = threading.Thread(target=read_stdout, args=(proc, handle_new_line,proc), daemon=True)
    thread.start()
    return proc, thread

message_queue = queue.Queue()
def process_incoming_json(type, json_string):
    try:
        parsed_data = json.loads(json_string)
        message_queue.put(parsed_data)  # Put parsed data into the queue for processing
    except json.JSONDecodeError:
        a=1
        #print("Invalid JSON string")

def startSimulation(pathName, fedName):
    manager = ProcessManager(process_incoming_json)
    full_path=os.path.join(os.getcwd(),pathName)
    message = f"LOAD {full_path};"
    manager.write_message(message)
    message = f"STARTFEDERATE {fedName};"
    manager.write_message(message)
    #message = f"RUNMODEL;"
    #manager.write_message(message)
    return manager


def graceful_shutdown(proc):
    print("Graceful shutdown…")
    send_control(proc, "CONTROLSIGNAL ALL ENDFEDERATE\n")
    time.sleep(1.5)  # short grace period


print("Starting rtig...")
rtig_process = subprocess.Popen(["rtig"])
time.sleep(2)

listener_proc, listener_thread = launch_listener()
time.sleep(2)
simA = startSimulation("SimA.jstrx", "SimA")
message = f"RUNMODEL;"
simA.write_message(message)
simB = startSimulation("SimB.jstrx", "SimB")
message = f"RUNMODEL;"
simB.write_message(message)



running = True
while running:
    try:
        kind, payload = events.get(timeout=0.1)  # wait briefly for events
    except queue.Empty:
        continue

    if kind == "shutdown":
        graceful_shutdown(listener_proc)
        simA.write_message("CLOSE;")
        time.sleep(2)
        simA.cleanup()
        simB.write_message("CLOSE;")
        time.sleep(2)
        simB.cleanup()
        running = False