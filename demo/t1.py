def avg(first, *rest):
    return (first + sum(rest)) / (1 + len(rest))



print(avg(2,3,8,9))