#include <stdio.h>

int main(){
    
    struct{
        char *name;
        int num;
        int age;
        char group;
        float score;
    } stu1;

    stu1.name = 'xx';
    stu1.num = 12;
    stu1.age = 18;
    stu1.group ='A';
    stu1.score = 136.5;

    printf("%s,%d",stu1.name,stu1.num);

    return 0;
}