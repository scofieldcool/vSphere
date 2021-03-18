#include <stdio.h>

struct stu{
    char *name;
    int num;
    int age;
    char group;
    float score;

}stus[] ={
    {"xx",5,6,'t',123.4},
    {"x",5,6,'t',13.4}
};

void average(struct stu *ps, int len);

int main(){
    int len = sizeof(stus) / sizeof(struct stu);
    average(stus, len);
    return 0;

}

void average(struct stu *ps, int len){
    int i, num_140 =0;
    float average, sum =0;
    for(i=0; i<len; i++){
        sum += (ps + i) -> score;
        if((ps + i)-> score < 140) num_140++;
    }

    printf("%d", num_140);
}
