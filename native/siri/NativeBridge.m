// Initial native-delivery fixture. Real utterances pass through unchanged.
#import <Foundation/Foundation.h>
#import <objc/message.h>
#import <objc/runtime.h>
#import <sys/sysctl.h>
#import <string.h>
#import <unistd.h>

static void (*originalStart)(id,SEL,id,id);
static const char *testFlag="/var/mobile/Library/Assistant/ICBSiriBridge/native-self-test";

static BOOL methodMatches(Class cls,const char *name,const char *types) {
    Method method=class_getInstanceMethod(cls,sel_registerName(name));
    return method&&strcmp(method_getTypeEncoding(method),types)==0;
}
static id get(id object,const char *name) {
    return ((id(*)(id,SEL))objc_msgSend)(object,sel_registerName(name));
}
static void set(id object,const char *name,id value) {
    ((void(*)(id,SEL,id))objc_msgSend)(object,sel_registerName(name),value);
}
static void deliver(id client,NSString *ref) {
    id view=[[objc_getClass("SAUIAssistantUtteranceView") alloc] init];
    set(view,"setText:",@"ICB_NATIVE_REPLY_20261105");
    id command=[[objc_getClass("SAUIAddViews") alloc] init];
    set(command,"setViews:",@[view]);
    set(command,"setDialogPhase:",@"Completion");
    set(command,"setAceId:",NSUUID.UUID.UUIDString);
    if(ref)set(command,"setRefId:",ref);
    void (^reply)(id,id)=^(id result,id error){(void)result;(void)error;};
    ((void(*)(id,SEL,id,id))objc_msgSend)(client,sel_registerName("adRequestDidReceiveCommand:reply:"),command,reply);
    ((void(*)(id,SEL,BOOL,id))objc_msgSend)(client,sel_registerName("adRequestDidCompleteWithSuccess:error:"),YES,nil);
}
static void start(id self,SEL cmd,id info,id delegate) {
    if(access(testFlag,R_OK)!=0||!methodMatches([info class],"text","@16@0:8")) {
        originalStart(self,cmd,info,delegate);return;
    }
    id value=get(info,"text");
    if(![value isKindOfClass:NSString.class]||![value isEqual:@"ICB_NATIVE_SIRI_TEST_20261105"]||
       ![delegate isKindOfClass:objc_getClass("ADClientConnection")]) {
        originalStart(self,cmd,info,delegate);return;
    }
    id identifier=methodMatches([info class],"uuid","@16@0:8")?get(info,"uuid"):nil;
    NSString *reference=[identifier isKindOfClass:NSUUID.class]?[identifier UUIDString]:nil;
    dispatch_queue_t queue=((id(*)(id,SEL))objc_msgSend)([self class],sel_registerName("sharedQueue"));
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC),queue,^{deliver(delegate,reference);});
}
__attribute__((constructor)) static void loadBridge(void) {
    if(strcmp(getprogname(),"assistantd"))return;
    char build[64]={0};size_t length=sizeof(build);sysctlbyname("kern.osversion",build,&length,NULL,0);
    if(strcmp(build,"20B101"))return;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,2*NSEC_PER_SEC),dispatch_get_main_queue(),^{
        Class center=objc_getClass("ADCommandCenter"),client=objc_getClass("ADClientConnection");
        Class add=objc_getClass("SAUIAddViews"),view=objc_getClass("SAUIAssistantUtteranceView");
        if(!methodMatches(center,"_startRequest:withDelegate:","v32@0:8@16@24")||
           !methodMatches(object_getClass(center),"sharedQueue","@16@0:8")||
           !methodMatches(client,"adRequestDidReceiveCommand:reply:","v32@0:8@16@?24")||
           !methodMatches(client,"adRequestDidCompleteWithSuccess:error:","v28@0:8B16@20")||
           !methodMatches(add,"setViews:","v24@0:8@16")||!methodMatches(add,"setDialogPhase:","v24@0:8@16")||
           !methodMatches(add,"setAceId:","v24@0:8@16")||!methodMatches(add,"setRefId:","v24@0:8@16")||
           !methodMatches(view,"setText:","v24@0:8@16"))return;
        Method method=class_getInstanceMethod(center,sel_registerName("_startRequest:withDelegate:"));
        originalStart=(void(*)(id,SEL,id,id))method_setImplementation(method,(IMP)start);
    });
}
