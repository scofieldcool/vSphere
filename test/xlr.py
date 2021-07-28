from openpyxl import load_workbook

workbook = load_workbook(filename = "data.xlsx")
sheet = workbook.active

def str_handel(config):
    str1 = ''
    for row in config:
        for cell in row:
            if cell.value == None:
                break
            str1 = str1 + str(cell.value) + ' '
        if str1:
            str1 = str1 + ';'

    return str1

for i in range(3,23):
    start = 'A{}'.format(i)
    end = 'L{}'.format(i)
    config = sheet[start:end]
    str1 = str_handel(config)
    with open('out.txt','a+') as f:
            f.write(str1)
            f.write('\r\n')
            f.close()


