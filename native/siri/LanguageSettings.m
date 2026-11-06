// Fixed language operation; no raw preference-file writes or speech capture.
#import <Foundation/Foundation.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import <dlfcn.h>
#import <sys/sysctl.h>
#import <string.h>
#import <unistd.h>

static BOOL matches(Class cls,const char *name,const char *types){
    Method method=class_getInstanceMethod(cls,sel_registerName(name));
    return method&&!strcmp(method_getTypeEncoding(method),types);
}
static id get(id object,const char *name){return ((id(*)(id,SEL))objc_msgSend)(object,sel_registerName(name));}
static int finish(NSString *status,NSString *reason,NSDictionary *data){
    NSMutableDictionary *out=[@{@"schema":@"ios-control-bridge.siri-language.v1",@"source":@"AssistantServices.AFPreferences",@"status":status,@"observed_at_unix":@(NSDate.date.timeIntervalSince1970)} mutableCopy];
    if(reason)out[@"reason"]=reason;if(data)[out addEntriesFromDictionary:data];
    NSData *json=[NSJSONSerialization dataWithJSONObject:out options:0 error:NULL];fwrite(json.bytes,1,json.length,stdout);fputc('\n',stdout);
    return [status isEqual:@"verified"]?0:([status isEqual:@"partial"]?2:([status isEqual:@"unavailable"]?3:4));
}
int main(int argc,char *argv[]){@autoreleasepool{@try{
    BOOL write=argc==3&&!strcmp(argv[1],"set-language");
    if(!write&&(argc!=2||strcmp(argv[1],"get")))return finish(@"error",@"invalid_arguments",nil);
    NSString *requested=write?[NSString stringWithUTF8String:argv[2]]:nil;
    if(write&&![@[@"zh-CN",@"en-US"] containsObject:requested])return finish(@"error",@"unsupported_language",nil);
    char build[64]={0};size_t length=sizeof(build);sysctlbyname("kern.osversion",build,&length,NULL,0);
    if(strcmp(build,"20B101"))return finish(@"unavailable",@"unverified_os_build",nil);
    if(getuid()!=501)return finish(@"unavailable",@"requires_mobile_user",nil);
    if(!dlopen("/System/Library/PrivateFrameworks/AssistantServices.framework/AssistantServices",RTLD_NOW))return finish(@"unavailable",@"framework_missing",nil);
    Class cls=objc_getClass("AFPreferences");
    if(!matches(object_getClass(cls),"sharedPreferences","@16@0:8")||!matches(cls,"languageCode","@16@0:8")||
       !matches(cls,"setLanguageCode:","v24@0:8@16")||!matches(cls,"synchronize","v16@0:8"))return finish(@"unavailable",@"unsupported_abi",nil);
    id prefs=get(cls,"sharedPreferences");id before=get(prefs,"languageCode");
    if(![before isKindOfClass:NSString.class])return finish(@"unavailable",@"language_unreadable",nil);
    if(!write)return finish(@"verified",nil,@{@"language_code":before});
    if(![before isEqual:requested]){
        ((void(*)(id,SEL,id))objc_msgSend)(prefs,sel_registerName("setLanguageCode:"),requested);
        ((void(*)(id,SEL))objc_msgSend)(prefs,sel_registerName("synchronize"));
    }
    id after=get(prefs,"languageCode");
    NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:2];
    while(![after isEqual:requested]&&deadline.timeIntervalSinceNow>0){
        [NSRunLoop.currentRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:.05]];
        after=get(prefs,"languageCode");
    }
    NSDictionary *data=@{@"before":before,@"requested":requested,@"readback":[after isKindOfClass:NSString.class]?after:@"",@"language_code":[after isKindOfClass:NSString.class]?after:@""};
    return [after isEqual:requested]?finish(@"verified",nil,data):finish(@"partial",@"readback_mismatch",data);
}@catch(NSException *exception){(void)exception;return finish(@"error",@"native_exception",nil);}}}
