// Explicit synthetic text request; does not open Siri UI or record microphone.
#import <Foundation/Foundation.h>
#import <objc/message.h>
#import <objc/runtime.h>
#import <dlfcn.h>
#import <string.h>

@interface FixtureDelegate : NSObject
@property(nonatomic,strong) NSMutableArray *events;
@end
@implementation FixtureDelegate
- (instancetype)init {if((self=[super init]))_events=[NSMutableArray array];return self;}
- (void)assistantConnectionRequestWillStart:(id)connection {(void)connection;[self.events addObject:@"request_will_start"];}
- (void)assistantConnection:(id)connection receivedCommand:(id)command completion:(void (^)(id))completion {
    (void)connection;[self.events addObject:NSStringFromClass([command class])];if(completion)completion(nil);
}
- (void)assistantConnection:(id)connection requestFailedWithError:(NSError *)error requestClass:(id)requestClass {
    (void)connection;(void)requestClass;
    [self.events addObject:[NSString stringWithFormat:@"request_failed:%@:%ld",error.domain,(long)error.code]];
}
- (void)assistantConnectionRequestFinished:(id)connection {(void)connection;[self.events addObject:@"request_finished"];}
@end
int main(void){@autoreleasepool{
    void *handle=dlopen("/System/Library/PrivateFrameworks/AssistantServices.framework/AssistantServices",RTLD_NOW);
    Class cls=objc_getClass("AFConnection");SEL start=sel_registerName("startRequestWithText:");
    Method method=class_getInstanceMethod(cls,start);
    if(!handle||!method||strcmp(method_getTypeEncoding(method),"v24@0:8@16"))return 2;
    id connection=[[cls alloc] init];FixtureDelegate *delegate=[FixtureDelegate new];
    ((void(*)(id,SEL,id))objc_msgSend)(connection,sel_registerName("setDelegate:"),delegate);
    ((void(*)(id,SEL,id))objc_msgSend)(connection,start,@"What is one plus one? Reply with the number only.");
    NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:8];
    while(deadline.timeIntervalSinceNow>0)[NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.1]];
    ((void(*)(id,SEL))objc_msgSend)(connection,sel_registerName("cancelRequest"));
    NSData *json=[NSJSONSerialization dataWithJSONObject:@{@"synthetic_request_submitted":@YES,@"delegate_events":delegate.events,@"microphone_requested":@NO} options:0 error:NULL];fwrite(json.bytes,1,json.length,stdout);fputc('\n',stdout);
}return 0;}
