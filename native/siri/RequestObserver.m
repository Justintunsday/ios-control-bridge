// Development-only routing observer. Records method/type metadata, never text.
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <sys/sysctl.h>
#import <sys/stat.h>
#import <string.h>
#import <fcntl.h>
#import <unistd.h>

static NSString *const directory=@"/var/mobile/Library/Assistant/ICBSiriBridge";
static void (*startOriginal)(id,SEL,id,id);
static void (*recognitionOriginal)(id,SEL,id,id);
static void (*clientStartOriginal)(id,SEL,id,id);
static void (*receiveOriginal)(id,SEL,id,id);
static void (*completeOriginal)(id,SEL,BOOL,id);
static void (*speechOriginal)(id,SEL,id,id,id);
static void (*sendOriginal)(id,SEL,id,BOOL,BOOL);

static NSString *blockSignature(id value) {
    if(!value)return @"nil";
    struct Layout { void *isa; int flags,reserved; void *invoke; void *descriptor; };
    const struct Layout *block=(__bridge const void *)value;
    if(!(block->flags&(1<<30)))return @"unavailable";
    const uint8_t *p=block->descriptor;
    if(!p)return @"unavailable";
    p+=sizeof(unsigned long)*2;
    if(block->flags&(1<<25))p+=sizeof(void *)*2;
    const char *signature=*(const char *const *)p;
    return signature?[NSString stringWithUTF8String:signature]:@"unavailable";
}
static void event(NSString *name,id first,id second,BOOL isBlock) {
    @autoreleasepool {
        NSMutableDictionary *record=[@{@"event":name,@"unix":@(NSDate.date.timeIntervalSince1970),@"first_class":first?NSStringFromClass([first class]):@"nil",@"second_class":second?NSStringFromClass([second class]):@"nil"} mutableCopy];
        if(isBlock&&second)record[@"block_signature"]=blockSignature(second);
        if(first&&([name isEqual:@"client_start"]||[name isEqual:@"start_request"]||[name isEqual:@"speech_recognized"])) {
            unsigned count=0;Method *list=class_copyMethodList(object_getClass(first),&count);NSMutableArray *methods=[NSMutableArray array];
            for(unsigned i=0;i<count;++i){NSString *selector=NSStringFromSelector(method_getName(list[i]));if(selector.length<120)[methods addObject:@{@"selector":selector,@"encoding":[NSString stringWithUTF8String:method_getTypeEncoding(list[i])]}];}
            free(list);record[@"first_class_methods"]=methods;
        }
        NSMutableData *json=[[NSJSONSerialization dataWithJSONObject:record options:0 error:NULL] mutableCopy];
        [json appendBytes:"\n" length:1];
        NSString *path=[directory stringByAppendingPathComponent:@"routing-metadata.jsonl"];
        int fd=open(path.fileSystemRepresentation,O_WRONLY|O_CREAT|O_APPEND|O_NOFOLLOW,0600);
        if(fd>=0){struct stat st;if(fstat(fd,&st)==0&&st.st_size<512*1024)write(fd,json.bytes,json.length);close(fd);}
    }
}
static void start(id self,SEL cmd,id request,id delegate){event(@"start_request",request,delegate,NO);startOriginal(self,cmd,request,delegate);}
static void recognize(id self,SEL cmd,id recognized,id completion){event(@"speech_recognized",recognized,completion,YES);recognitionOriginal(self,cmd,recognized,completion);}
static void clientStart(id self,SEL cmd,id info,id completion){event(@"client_start",info,completion,YES);clientStartOriginal(self,cmd,info,completion);}
static void receive(id self,SEL cmd,id command,id reply){event(@"client_receive",command,reply,YES);receiveOriginal(self,cmd,command,reply);}
static void complete(id self,SEL cmd,BOOL success,id error){event(success?@"client_complete_success":@"client_complete_failure",error,nil,NO);completeOriginal(self,cmd,success,error);}
static void speech(id self,SEL cmd,id recognition,id model,id session){event(@"client_speech",recognition,nil,NO);speechOriginal(self,cmd,recognition,model,session);}
static void send(id self,SEL cmd,id command,BOOL opportunistic,BOOL log){event(@"session_send",command,nil,NO);sendOriginal(self,cmd,command,opportunistic,log);}
static BOOL hook(const char *name,const char *selector,const char *encoding,IMP replacement,IMP *original) {
    Class cls=objc_getClass(name);SEL sel=sel_registerName(selector);Method method=class_getInstanceMethod(cls,sel);
    if(!method||strcmp(method_getTypeEncoding(method),encoding))return NO;
    *original=method_setImplementation(method,replacement);return *original!=NULL;
}
__attribute__((constructor)) static void loadObserver(void) {
    if(strcmp(getprogname(),"assistantd"))return;
    char build[64]={0};size_t size=sizeof(build);sysctlbyname("kern.osversion",build,&size,NULL,0);if(strcmp(build,"20B101"))return;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,2*NSEC_PER_SEC),dispatch_get_main_queue(),^{
        BOOL ok=YES;
        ok&=hook("ADCommandCenter","_startRequest:withDelegate:","v32@0:8@16@24",(IMP)start,(IMP *)&startOriginal);
        ok&=hook("ADCommandCenter","handleSpeechRecognized:completion:","v32@0:8@16@?24",(IMP)recognize,(IMP *)&recognitionOriginal);
        ok&=hook("ADClientConnection","startRequestWithInfo:completion:","Vv32@0:8@16@?24",(IMP)clientStart,(IMP *)&clientStartOriginal);
        ok&=hook("ADClientConnection","adRequestDidReceiveCommand:reply:","v32@0:8@16@?24",(IMP)receive,(IMP *)&receiveOriginal);
        ok&=hook("ADClientConnection","adRequestDidCompleteWithSuccess:error:","v28@0:8B16@20",(IMP)complete,(IMP *)&completeOriginal);
        ok&=hook("ADClientConnection","adSpeechRecognized:usingSpeechModel:sessionUUID:","v40@0:8@16@24@32",(IMP)speech,(IMP *)&speechOriginal);
        ok&=hook("ADSessionManager","sendCommand:opportunistically:logEvent:","v32@0:8@16B24B28",(IMP)send,(IMP *)&sendOriginal);
        event(ok?@"observer_ready":@"observer_partial",nil,nil,NO);
    });
}
