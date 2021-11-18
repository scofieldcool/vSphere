import re


test = 'AaB12_a1'
if re.match('^[a-zA-Z](?!.*?_$)(?=.*_)[a-zA-Z0-9_]*$', test):
    print(test)