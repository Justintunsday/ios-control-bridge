// Explicit synthetic text request; does not open Siri UI or record microphone.
#import <Foundation/Foundation.h>
#import <objc/message.h>
#import <objc/runtime.h>
#import <dlfcn.h>
#import <string.h>

@interface FixtureDelegate : NSObject
@property(nonatomic,strong) NSMutableArray *events;
@property(nonatomic,strong) NSMutableArray *utterances;
@end
@implementation FixtureDelegate
- (instancetype)init {if((self=[super init])){_events=[NSMutableArray array];_utterances=[NSMutableArray array];}return self;}
- (void)assistantConnectionRequestWillStart:(id)connection {(void)connection;[self.events addObject:@"request_will_start"];}
- (void)assistantConnection:(id)connection receivedCommand:(id)command completion:(void (^)(id))completion {
    (void)connection;[self.events addObject:NSStringFromClass([command class])];
    Method views=class_getInstanceMethod([command class],sel_registerName("views"));
    if(views&&!strcmp(method_getTypeEncoding(views),"@16@0:8")){
        id list=((id(*)(id,SEL))objc_msgSend)(command,sel_registerName("views"));
        if([list isKindOfClass:NSArray.class])for(id view in list){
            Method text=class_getInstanceMethod([view class],sel_registerName("text"));
            if(text&&!strcmp(method_getTypeEncoding(text),"@16@0:8")){
                id value=((id(*)(id,SEL))objc_msgSend)(view,sel_registerName("text"));
                if([value isKindOfClass:NSString.class]&&[value length]<2000)[self.utterances addObject:value];
            }
        }
    }
    if(completion)completion(nil);
}
- (void)assistantConnection:(id)connection requestFailedWithError:(NSError *)error requestClass:(id)requestClass {
    (void)connection;(void)requestClass;
    [self.events addObject:[NSString stringWithFormat:@"request_failed:%@:%ld:%@",error.domain,(long)error.code,[error.localizedDescription substringToIndex:MIN((NSUInteger)240,error.localizedDescription.length)]]];
}
- (void)assistantConnectionRequestFinished:(id)connection {(void)connection;[self.events addObject:@"request_finished"];}
@end
int main(int argc,char *argv[]){@autoreleasepool{
    void *handle=dlopen("/System/Library/PrivateFrameworks/AssistantServices.framework/AssistantServices",RTLD_NOW);
    Class cls=objc_getClass("AFConnection");SEL start=sel_registerName("startRequestWithText:");
    Method method=class_getInstanceMethod(cls,start);
    if(!handle||!method||strcmp(method_getTypeEncoding(method),"v24@0:8@16"))return 2;
    id connection=[[cls alloc] init];FixtureDelegate *delegate=[FixtureDelegate new];
    ((void(*)(id,SEL,id))objc_msgSend)(connection,sel_registerName("setDelegate:"),delegate);
    NSString *question=argc==2?[NSString stringWithUTF8String:argv[1]]:@"What is one plus one? Reply with the number only.";
    ((void(*)(id,SEL,id))objc_msgSend)(connection,start,question);
    NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:8];
    while(deadline.timeIntervalSinceNow>0)[NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.1]];
    ((void(*)(id,SEL))objc_msgSend)(connection,sel_registerName("cancelRequest"));
    NSData *json=[NSJSONSerialization dataWithJSONObject:@{@"synthetic_request_submitted":@YES,@"delegate_events":delegate.events,@"received_utterances":delegate.utterances,@"microphone_requested":@NO} options:0 error:NULL];fwrite(json.bytes,1,json.length,stdout);fputc('\n',stdout);
}return 0;}
