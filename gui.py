import functions
import PySimpleGUI

label = PySimpleGUI.Text('Type in a To-Do')
input_box = PySimpleGUI.InputText(tooltip='Enter todo',key='todo')
add_button = PySimpleGUI.Button('Add')
list_box = PySimpleGUI.Listbox(values=functions.get_todos(),key='todos',
                               enable_events=True, size=[45, 10])
edit_button = PySimpleGUI.Button('Edit')

window = PySimpleGUI.Window('My To-Do-App',
                            layout=[[label], [input_box, add_button],[list_box,edit_button]],
                            font = ('Helvetica',20)
                            )
while True:
    event,values = window.read()
    print(event)
    print(values)
    print(values['todos'])
    match event:
        case 'Add':
            todos = functions.get_todos()
            new_todo = values['todo'] + '\n'
            todos.append(new_todo)
            functions.write_todos(todos)
            window['todos'].update(values=todos)
        case 'Edit':
            todo_to_edit = values['todos'][0]
            new_todo = values['todo']

            todos = functions.get_todos()
            index = todos.index(todo_to_edit)
            todos[index] = new_todo
            functions.write_todos(todos)
            window['todos'].update(values=todos)

        case 'Todos':
            window['todo'].update(value=values['todos'][0])

        case PySimpleGUI.WIN_CLOSED:
            break
window.close()



