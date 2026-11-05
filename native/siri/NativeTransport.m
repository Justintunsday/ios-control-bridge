// Optional 20B101 Siri transport. Uses stock recognition, UI and TTS views.
#import "SiriRuntime.h"
#import <arpa/inet.h>
#import <errno.h>
#import <fcntl.h>
#import <poll.h>
#import <sys/socket.h>
#import <sys/stat.h>
#import <sys/sysctl.h>
#import <sys/un.h>
#import <time.h>
#import <unistd.h>

static const char *directory="/var/mobile/Library/Assistant/ICBSiriBridge";
static const char *endpoint="/var/mobile/Library/Assistant/ICBSiriBridge/bridge.sock";
static NSString *const protocol=@"ios-control-bridge.siri.v1";
static void (*originalStart)(id,SEL,id,id);
static void (*originalRecognize)(id,SEL,id,id);
static void (*originalSpeechStart)(id,SEL,id,id,id,id);
static void (*originalReceive)(id,SEL,id,id);
static void (*originalComplete)(id,SEL,BOOL,id);
static void (*originalDismiss)(id,SEL);
static void (*originalDisconnect)(id,SEL);
static void (*originalCancel)(id,SEL,long long,id);
static NSObject *turnLock;

@interface ICBExternalSiriTurn : NSObject
@property(nonatomic,strong) id client;
@property(nonatomic,copy) NSString *identifier;
@property(nonatomic,copy) NSString *reference;
@property(nonatomic) BOOL valid;
@end
@implementation ICBExternalSiriTurn
@end
static ICBExternalSiriTurn *currentTurn;

static double monotonic(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
static BOOL transfer(int fd,void *buffer,size_t size,BOOL writing,double deadline){
    uint8_t *bytes=buffer;
    while(size){
        double remaining=deadline-monotonic();if(remaining<=0)return NO;
        struct pollfd item={fd,writing?POLLOUT:POLLIN,0};
        int ready=poll(&item,1,(int)(remaining*1000));
        if(ready<0&&errno==EINTR)continue;
        if(ready<=0||(item.revents&(POLLERR|POLLNVAL)))return NO;
        ssize_t count=writing?send(fd,bytes,size,0):recv(fd,bytes,size,0);
        if(count<0&&(errno==EINTR||errno==EAGAIN))continue;
        if(count<=0)return NO;
        bytes+=count;size-=(size_t)count;
    }
    return YES;
}
static NSDictionary *rpc(NSDictionary *request){
    NSData *body=[NSJSONSerialization dataWithJSONObject:request options:0 error:NULL];
    if(!body.length||body.length>65536)return nil;
    int fd=socket(AF_UNIX,SOCK_STREAM,0);if(fd<0)return nil;
    int one=1;setsockopt(fd,SOL_SOCKET,SO_NOSIGPIPE,&one,sizeof(one));
    fcntl(fd,F_SETFD,FD_CLOEXEC);fcntl(fd,F_SETFL,O_NONBLOCK);
    struct sockaddr_un address={0};address.sun_family=AF_UNIX;address.sun_len=sizeof(address);
    strlcpy(address.sun_path,endpoint,sizeof(address.sun_path));
    double deadline=monotonic()+42;BOOL ok=YES;
    if(connect(fd,(struct sockaddr *)&address,sizeof(address))<0){
        if(errno!=EINPROGRESS)ok=NO;
        else{
            struct pollfd item={fd,POLLOUT,0};int error=0;socklen_t length=sizeof(error);
            ok=poll(&item,1,500)>0&&getsockopt(fd,SOL_SOCKET,SO_ERROR,&error,&length)==0&&error==0;
        }
    }
    uid_t user=(uid_t)-1;gid_t group=(gid_t)-1;
    ok=ok&&getpeereid(fd,&user,&group)==0&&user==0;
    uint32_t length=htonl((uint32_t)body.length);
    ok=ok&&transfer(fd,&length,4,YES,deadline)&&transfer(fd,(void *)body.bytes,body.length,YES,deadline);
    ok=ok&&transfer(fd,&length,4,NO,deadline);length=ntohl(length);
    NSMutableData *response=ok&&length>0&&length<=65536?[NSMutableData dataWithLength:length]:nil;
    ok=response&&transfer(fd,response.mutableBytes,response.length,NO,deadline);
    close(fd);if(!ok)return nil;
    id result=[NSJSONSerialization JSONObjectWithData:response options:0 error:NULL];
    if(![result isKindOfClass:NSDictionary.class]||![result[@"protocol"] isEqual:protocol]||
       ![result[@"id"] isEqual:request[@"id"]]||![result[@"text"] isKindOfClass:NSString.class]||
       ![result[@"text"] length]||[result[@"text"] length]>4096)return nil;
    return result;
}
static BOOL enabled(void){
    char flag[256];snprintf(flag,sizeof(flag),"%s/enabled",directory);
    struct stat file,sock;
    return lstat(flag,&file)==0&&S_ISREG(file.st_mode)&&file.st_uid==getuid()&&
        !(file.st_mode&0077)&&lstat(endpoint,&sock)==0&&S_ISSOCK(sock.st_mode)&&sock.st_uid==getuid();
}
static void metadata(const char *event){
    // No utterance, answer, session ID or credentials are written to this log.
    char path[256],line[192];snprintf(path,sizeof(path),"%s/native-events.jsonl",directory);
    int count=snprintf(line,sizeof(line),"{\"event\":\"%s\",\"unix\":%lld}\n",event,(long long)time(NULL));
    int fd=open(path,O_WRONLY|O_APPEND|O_CREAT|O_NOFOLLOW,0600);
    if(fd>=0){struct stat st;if(fstat(fd,&st)==0&&S_ISREG(st.st_mode)&&st.st_size<262144)write(fd,line,(size_t)count);close(fd);}
}
static void invalidate(id client){
    @synchronized(turnLock){if(currentTurn&&(!client||currentTurn.client==client)){currentTurn.valid=NO;currentTurn=nil;}}
}
static BOOL owns(ICBExternalSiriTurn *turn){@synchronized(turnLock){return currentTurn==turn&&turn.valid;}}
static BOOL ownsClient(id client){@synchronized(turnLock){return currentTurn&&currentTurn.valid&&currentTurn.client==client;}}
static dispatch_queue_t sharedQueue(id center){return ((id(*)(id,SEL))objc_msgSend)([center class],sel_registerName("sharedQueue"));}
static void deliver(ICBExternalSiriTurn *turn,NSString *text){
    if(!owns(turn)||!enabled())return;
    id view=[[objc_getClass("SAUIAssistantUtteranceView") alloc] init];
    ICBSet(view,"setText:",text);ICBSet(view,"setSpeakableText:",text);
    id command=[[objc_getClass("SAUIAddViews") alloc] init];
    ICBSet(command,"setViews:",@[view]);ICBSet(command,"setDialogPhase:",@"Completion");
    ICBSet(command,"setAceId:",NSUUID.UUID.UUIDString);
    if(turn.reference)ICBSet(command,"setRefId:",turn.reference);
    void (^reply)(id,id)=^(id result,id error){(void)result;(void)error;};
    originalReceive(turn.client,sel_registerName("adRequestDidReceiveCommand:reply:"),command,reply);
    originalComplete(turn.client,sel_registerName("adRequestDidCompleteWithSuccess:error:"),YES,nil);
    metadata("native_reply_delivered");
    // Retain ownership until dismissal/new request so late stock commands stay suppressed.
}
static ICBExternalSiriTurn *begin(id client,NSString *reference){
    ICBExternalSiriTurn *turn=[ICBExternalSiriTurn new];turn.client=client;
    turn.identifier=NSUUID.UUID.UUIDString.lowercaseString;turn.reference=reference;turn.valid=YES;
    @synchronized(turnLock){currentTurn.valid=NO;currentTurn=turn;}
    return turn;
}
static void ask(id center,ICBExternalSiriTurn *turn,NSString *text){
    dispatch_queue_t queue=sharedQueue(center);
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY,0),^{@autoreleasepool{
        if(!owns(turn)||!enabled())return;
        NSDictionary *result=rpc(@{@"protocol":protocol,@"op":@"ask",@"id":turn.identifier,@"text":text});
        NSString *answer=result[@"text"]?:@"暂时无法确认 OpenCode 的处理结果。请在 BridgeChat 查看，这条请求不会自动重发。";
        metadata(result?"backend_reply_received":"backend_reply_unconfirmed");
        dispatch_async(queue,^{deliver(turn,answer);});
    }});
}
static void start(id self,SEL cmd,id info,id delegate){
    invalidate(nil);
    id text=ICBGet(info,"text");
    if(!enabled()||![text isKindOfClass:NSString.class]||![text length]||[text length]>4096||
       ![delegate isKindOfClass:objc_getClass("ADClientConnection")]){originalStart(self,cmd,info,delegate);return;}
    id identifier=ICBGet(info,"uuid");NSString *ref=[identifier isKindOfClass:NSUUID.class]?[identifier UUIDString]:nil;
    ICBExternalSiriTurn *turn=begin(delegate,ref);metadata("typed_query_intercepted");ask(self,turn,text);
}
static void recognize(id self,SEL cmd,id recognized,id completion){
    const char *types=ICBBlockTypes(completion);
    NSString *text=enabled()?ICBRecognitionText(recognized):nil;
    id client=text?ICBGet(self,"_requestDelegate"):nil;
    if(![client isKindOfClass:objc_getClass("ADClientConnection")])client=text?ICBGet(self,"_currentClient"):nil;
    // Captured from the real 20B101 microphone callback; do not guess block arguments.
    if(!text||!types||strcmp(types,"v24@?0@\"SABaseCommand\"8@\"NSError\"16")||
       ![client isKindOfClass:objc_getClass("ADClientConnection")]){originalRecognize(self,cmd,recognized,completion);return;}
    id ref=ICBGet(recognized,"refId");
    ICBExternalSiriTurn *turn=begin(client,[ref isKindOfClass:NSString.class]?ref:nil);
    metadata("voice_query_intercepted");
    // Do not run Apple's fulfillment handler and OpenCode for the same utterance.
    ((void(^)(id,id))completion)(nil,nil);
    dispatch_async(sharedQueue(self),^{
        if(!owns(turn))return;
        ((void(*)(id,SEL))objc_msgSend)(self,sel_registerName("cancelCurrentRequest"));
        ask(self,turn,text);
    });
}
static void speechStart(id self,SEL cmd,id delegate,id options,id session,id completion){
    invalidate(nil);originalSpeechStart(self,cmd,delegate,options,session,completion);
}
static void receive(id self,SEL cmd,id command,id reply){
    if(ownsClient(self)){
        const char *types=ICBBlockTypes(reply);
        if(!reply)return;
        if(types&&!strcmp(types,"v24@?0@\"AceObject<SAAceCommand>\"8@\"NSError\"16")){
            ((void(^)(id,id))reply)(nil,nil);metadata("stock_reply_suppressed");return;
        }
        // Unknown block ABI: invalidate routing rather than invoke an incompatible block.
        invalidate(self);
    }
    originalReceive(self,cmd,command,reply);
}
static void complete(id self,SEL cmd,BOOL success,id error){if(ownsClient(self))return;originalComplete(self,cmd,success,error);}
static void dismiss(id self,SEL cmd){invalidate(self);originalDismiss(self,cmd);}
static void disconnect(id self,SEL cmd){invalidate(self);originalDisconnect(self,cmd);}
static void cancel(id self,SEL cmd,long long reason,id error){invalidate(self);originalCancel(self,cmd,reason,error);}

__attribute__((constructor)) static void loadBridge(void){
    if(strcmp(getprogname(),"assistantd"))return;
    char build[64]={0};size_t length=sizeof(build);sysctlbyname("kern.osversion",build,&length,NULL,0);
    if(strcmp(build,"20B101"))return;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,2*NSEC_PER_SEC),dispatch_get_main_queue(),^{
        Class center=objc_getClass("ADCommandCenter"),client=objc_getClass("ADClientConnection");
        Class add=objc_getClass("SAUIAddViews"),view=objc_getClass("SAUIAssistantUtteranceView");
        struct Hook {Class cls;const char *selector,*encoding;IMP replacement;IMP *original;};
        struct Hook hooks[]={
            {center,"_startRequest:withDelegate:","v32@0:8@16@24",(IMP)start,(IMP *)&originalStart},
            {center,"handleSpeechRecognized:completion:","v32@0:8@16@?24",(IMP)recognize,(IMP *)&originalRecognize},
            {center,"_startSpeechRequestWithDelegate:withOptions:sessionUUID:completion:","v48@0:8@16@24@32@?40",(IMP)speechStart,(IMP *)&originalSpeechStart},
            {client,"adRequestDidReceiveCommand:reply:","v32@0:8@16@?24",(IMP)receive,(IMP *)&originalReceive},
            {client,"adRequestDidCompleteWithSuccess:error:","v28@0:8B16@20",(IMP)complete,(IMP *)&originalComplete},
            {client,"didDismissUI","Vv16@0:8",(IMP)dismiss,(IMP *)&originalDismiss},
            {client,"connectionDisconnected","v16@0:8",(IMP)disconnect,(IMP *)&originalDisconnect},
            {client,"cancelRequestForReason:withError:","Vv32@0:8q16@24",(IMP)cancel,(IMP *)&originalCancel},
        };
        for(unsigned i=0;i<sizeof(hooks)/sizeof(hooks[0]);i++)if(!ICBMethod(hooks[i].cls,hooks[i].selector,hooks[i].encoding)){metadata("unsupported_hook_abi");return;}
        if(!ICBMethod(object_getClass(center),"sharedQueue","@16@0:8")||
           !ICBMethod(center,"_requestDelegate","@16@0:8")||!ICBMethod(center,"_currentClient","@16@0:8")||
           !ICBMethod(center,"cancelCurrentRequest","v16@0:8")||
           !ICBMethod(add,"setViews:","v24@0:8@16")||!ICBMethod(add,"setDialogPhase:","v24@0:8@16")||
           !ICBMethod(add,"setAceId:","v24@0:8@16")||!ICBMethod(add,"setRefId:","v24@0:8@16")||
           !ICBMethod(view,"setText:","v24@0:8@16")||!ICBMethod(view,"setSpeakableText:","v24@0:8@16")){
            metadata("unsupported_delivery_abi");return;
        }
        turnLock=[NSObject new];
        for(unsigned i=0;i<sizeof(hooks)/sizeof(hooks[0]);i++)*hooks[i].original=method_setImplementation(class_getInstanceMethod(hooks[i].cls,sel_registerName(hooks[i].selector)),hooks[i].replacement);
        metadata("bridge_ready");
    });
}
