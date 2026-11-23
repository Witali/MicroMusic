#include <vector>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
extern "C" {float* source_input();int16_t* source_output();int source_capacity();int source_init(int,int,int);int source_push(int,int);}
int main(int argc,char**argv){
 if(argc!=5)return 1;int rate=std::atoi(argv[1]),target=std::atoi(argv[2]),channels=std::atoi(argv[3]),block=std::atoi(argv[4]);
 if(source_init(rate,target,channels)!=1||block<1||block>source_capacity())return 2;
 std::vector<float> input;float value;while(std::fread(&value,sizeof(value),1,stdin)==1)input.push_back(value);
 if(input.size()%channels)return 3;int frames=input.size()/channels;
 for(int at=0;at<frames;at+=block){int count=std::min(block,frames-at);for(int c=0;c<channels;c++)for(int j=0;j<count;j++)source_input()[c*source_capacity()+j]=input[(at+j)*channels+c];int n=source_push(count,0);if(n<0)return 4;std::fwrite(source_output(),2,n,stdout);}
 int n=source_push(0,1);if(n<0)return 5;std::fwrite(source_output(),2,n,stdout);return 0;
}
