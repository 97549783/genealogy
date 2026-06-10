# main.py
import ccc

print(ccc.articles)          # если в test.py есть some_variable = 42
ccc.some_function()              # если в test.py есть def some_function(): ...

message = "Привет из test.py!"

def get_data():
    return [1, 2, 3]
