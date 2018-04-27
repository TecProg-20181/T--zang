#!/usr/bin/env python3

import json
import requests
import time
import urllib

import sqlalchemy

import db
from db import Task

##Loading TOKEN from external file
with open('token.txt', 'r') as tokenfile:
  TOKEN = tokenfile.read()

URL = "https://api.telegram.org/bot{}/".format(TOKEN)

HELP = """
 /new NOME
 /todo ID
 /doing ID
 /done ID
 /delete ID
 /list
 /rename ID NOME
 /dependson ID ID...
 /duplicate ID
 /priority ID PRIORITY{low, medium, high}
 /help
"""

def get_url(url):
    response = requests.get(url)
    content = response.content.decode("utf8")
    return content

def get_json_from_url(url):
    content = get_url(url)
    js = json.loads(content)
    return js

def get_updates(offset=None):
    url = URL + "getUpdates?timeout=100"
    if offset:
        url += "&offset={}".format(offset)
    js = get_json_from_url(url)
    return js

def send_message(text, chat_id, reply_markup=None):
    text = urllib.parse.quote_plus(text)
    url = URL + "sendMessage?text={}&chat_id={}&parse_mode=Markdown".format(text, chat_id)
    if reply_markup:
        url += "&reply_markup={}".format(reply_markup)
    get_url(url)

def get_last_update_id(updates):
    update_ids = []
    for update in updates["result"]:
        update_ids.append(int(update["update_id"]))

    return max(update_ids)

def deps_text(task, chat, preceed=''):
    text = ''

    for i in range(len(task.dependencies.split(',')[:-1])):
        line = preceed
        query = db.session.query(Task).filter_by(id=int(task.dependencies.split(',')[:-1][i]), chat=chat)
        dep = query.one()

        icon = '\U0001F195'
        if dep.status == 'DOING':
            icon = '\U000023FA'
        elif dep.status == 'DONE':
            icon = '\U00002611'

        if i + 1 == len(task.dependencies.split(',')[:-1]):
            line += '└── [[{}]] {} {}\n'.format(dep.id, icon, dep.name)
            line += deps_text(dep, chat, preceed + '    ')
        else:
            line += '├── [[{}]] {} {}\n'.format(dep.id, icon, dep.name)
            line += deps_text(dep, chat, preceed + '│   ')

        text += line

    return text

def newTask(taskID, chat):

    task = Task(chat=chat, name=taskID, status='TODO', dependencies='', parents='', priority='')
    db.session.add(task)
    db.session.commit()
    send_message("New task *TODO* [[{}]] {}".format(task.id, task.name), chat)

def renameTask(taskID, chat):
    newName = ''

    if taskID != '':

        if len(taskID.split(' ', 1)) > 1:
            newName = taskID.split(' ', 1)[1]
                
        taskID = taskID.split(' ', 1)[0]

    if checkTaskId(taskID, chat):

        task, taskIDint = returnTask(taskID, chat)

        if newName == '':
            send_message("You want to modify task {}, but you didn't provide any new name".format(taskIDint), chat)
            return

        old_name = task.name
        task.name = newName
        db.session.commit()
        send_message("Task {} redefined from {} to {}".format(taskIDint, old_name, newName), chat)

def duplicateTask(taskID, chat):

    if checkTaskId(taskID, chat):

        task, taskIDint = returnTask(taskID, chat)

        duplicatedTask = Task(chat=task.chat, name=task.name, status=task.status, dependencies=task.dependencies,
                        parents=task.parents, priority=task.priority, duedate=task.duedate)
        db.session.add(duplicatedTask)

        for t in task.dependencies.split(',')[:-1]:
            qy = db.session.query(Task).filter_by(id=int(t), chat=chat)
            t = qy.one()
            t.parents += '{},'.format(duplicatedTask.id)

        db.session.commit()
        send_message("New task *TODO* [[{}]] {}".format(duplicatedTask.id, duplicatedTask.name), chat)

def deleteTask(taskID, chat):

    if checkTaskId(taskID, chat):

        task, taskIDint = returnTask(taskID, chat)

        for t in task.dependencies.split(',')[:-1]:
            qy = db.session.query(Task).filter_by(id=int(t), chat=chat)
            t = qy.one()
            t.parents = t.parents.replace('{},'.format(task.id), '')

        db.session.delete(task)
        db.session.commit()
        send_message("Task [[{}]] deleted".format(taskIDint), chat)

def dependson(taskID, chat):

    dependson = ''
    if taskID != '':
        if len(taskID.split(' ', 1)) > 1:
            dependson = taskID.split(' ', 1)[1]
        taskID = taskID.split(' ', 1)[0]

    if checkTaskId(taskID, chat):

        task, taskIDint = returnTask(taskID, chat)

        if dependson == '':
            for i in task.dependencies.split(',')[:-1]:
                i = int(i)
                q = db.session.query(Task).filter_by(id=i, chat=chat)
                t = q.one()
                t.parents = t.parents.replace('{},'.format(task.id), '')

            task.dependencies = ''
            send_message("Dependencies removed from task {}".format(taskIDint), chat)
        else:
            for depid in dependson.split(' '):
                if not depid.isdigit():
                    send_message("All dependencies ids must be numeric, and not {}".format(depid), chat)
                else:
                    depid = int(depid)
                    query = db.session.query(Task).filter_by(id=depid, chat=chat)
                    try:
                        taskdep = query.one()
                    except sqlalchemy.orm.exc.NoResultFound:
                        send_message("_404_ Task {} not found x.x".format(depid), chat)
                        continue

                    deplist = task.dependencies.split(',')

                    if str(depid) not in deplist:

                    	parentsList = task.parents.split(',')

                    	if str(taskdep.id) not in parentsList:
                    		task.dependencies += str(depid) + ','
                    		taskdep.parents += str(task.id) + ','
                    		for i in range(len(parentsList)):
                    			print(parentsList[i])
                    			taskdep.parents += parentsList[i] + ','
                    	else:
                    		send_message("Cannot do request. It will generate Circular dependencies", chat)


        db.session.commit()
        send_message("Task {} dependencies up to date".format(taskIDint), chat)

def setTaskPriority(taskID, chat):
    priority = ''
    if taskID != '':
        if len(taskID.split(' ', 1)) > 1:
            priority = taskID.split(' ', 1)[1]
        taskID = taskID.split(' ', 1)[0]

    if checkTaskId(taskID, chat):

        task, taskIDint = returnTask(taskID, chat)

        if priority == '':
            task.priority = ''
            send_message("_Cleared_ all priorities from task {}".format(taskIDint), chat)
        else:
            if priority.lower() not in ['high', 'medium', 'low']:
                send_message("The priority *must be* one of the following: high, medium, low", chat)
            else:
                task.priority = priority.lower()
                send_message("*Task {}* priority has priority *{}*".format(taskIDint, priority.lower()), chat)
        db.session.commit()

def setTaskStatus(command, taskID, chat):

    if command == '/todo':
        status = 'TODO'
    elif command == '/doing':
        status = 'DOING'
    elif command == '/done':
        status = 'DONE'

    if checkTaskId(taskID, chat):
        
        task, taskIDint = returnTask(taskID, chat)

        task.status = status
        db.session.commit()
        send_message("*{}* task [[{}]] {}".format(task.status, task.id, task.name), chat)

def listTodoTasks(chat):

    query = db.session.query(Task).filter_by(status='TODO', chat=chat).order_by(Task.id)
    botTODOMessage = '\n\U0001F195 *TODO*\n'

    for task in query.all():
        botTODOMessage += '[[{}]] {}\n'.format(task.id, task.name)

    return botTODOMessage

def listDoingTasks(chat):

    query = db.session.query(Task).filter_by(status='DOING', chat=chat).order_by(Task.id)
    botDOINGMessage = '\n\U000023FA *DOING*\n'

    for task in query.all():
        botDOINGMessage += '[[{}]] {}\n'.format(task.id, task.name)

    return botDOINGMessage

def listDoneTasks(chat):

    query = db.session.query(Task).filter_by(status='DONE', chat=chat).order_by(Task.id)
    botDONEMessage = '\n\U00002611 *DONE*\n'

    for task in query.all():
        botDONEMessage += '[[{}]] {}\n'.format(task.id, task.name)

    return botDONEMessage


def listTasks(chat):

    botStatusMessage = ''

    botStatusMessage += '\U0001F4CB Task List\n'
    query = db.session.query(Task).filter_by(parents='', chat=chat).order_by(Task.id)
    
            
    for task in query.all():
        icon = '\U0001F195'
        if task.status == 'DOING':
            icon = '\U000023FA'
        elif task.status == 'DONE':
            icon = '\U00002611'

        botStatusMessage += '[[{}]] {} {}'.format(task.id, icon, task.name)
        if task.priority != '':
            botStatusMessage += ' | priority: {}'.format(task.priority)
        botStatusMessage += '\n'
        botStatusMessage += deps_text(task, chat)

    send_message(botStatusMessage, chat)

    botStatusMessage = ''

    botStatusMessage += '\U0001F4DD _Status_\n'

    botStatusMessage += listTodoTasks(chat)
    botStatusMessage += listDoingTasks(chat)
    botStatusMessage += listDoneTasks(chat)

    send_message(botStatusMessage, chat)

def checkTaskId(taskID, chat):
    if not taskID.isdigit():
        return send_message("You must inform the task id", chat)
    else:
        taskIDint = int(taskID)
        query = db.session.query(Task).filter_by(id=taskIDint, chat=chat)
        try:
            task = query.one()
        except sqlalchemy.orm.exc.NoResultFound:
            send_message("_404_ Task {} not found x.x".format(taskIDint), chat)
            return False
        return True

def returnTask(taskID, chat):

    taskIDint = int(taskID)
    query = db.session.query(Task).filter_by(id=taskIDint, chat=chat)
    task = query.one()
    return task, taskIDint

def startBotFunctions(command, taskID, chat):
	
    if command == '/new':
        newTask(taskID, chat)

    elif command == '/rename':
        renameTask(taskID,chat)

    elif command == '/duplicate':
        duplicateTask(taskID, chat)

    elif command == '/delete':
        deleteTask(taskID, chat)   

    elif command == '/todo' or command == '/doing' or command == '/done':
        setTaskStatus(command, taskID, chat)

    elif command == '/list':
        listTasks(chat)

    elif command == '/dependson':
        dependson(taskID, chat)
                
    elif command == '/priority':
        setTaskPriority(taskID, chat)

    elif command == '/start':
        send_message("Welcome! Here is a list of things you can do.", chat)
        send_message(HELP, chat)

    elif command == '/help':
        send_message("Here is a list of things you can do.", chat)
        send_message(HELP, chat)

    else:
        send_message("I'm sorry dave. I'm afraid I can't do that.", chat)
    

def handle_updates(updates):

    for update in updates["result"]:

        if 'message' in update:
            message = update['message']
        elif 'edited_message' in update:
            message = update['edited_message']
        else:
            print('Can\'t process! {}'.format(update))
            return

        command = message["text"].split(" ", 1)[0]
        taskID = ''
        if len(message["text"].split(" ", 1)) > 1:
            taskID = message["text"].split(" ", 1)[1].strip()

        chat = message["chat"]["id"]

        print(command, taskID, chat)

        startBotFunctions(command, taskID, chat)


def main():
    last_update_id = None

    while True:
        print("Updates")
        updates = get_updates(last_update_id)

        if len(updates["result"]) > 0:
            last_update_id = get_last_update_id(updates) + 1
            handle_updates(updates)

        time.sleep(0.5)


if __name__ == '__main__':
    main()

