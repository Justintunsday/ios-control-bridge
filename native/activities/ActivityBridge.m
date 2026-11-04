#import "ActivityBridge.h"
#import <objc/runtime.h>
#import <objc/message.h>
#import <dlfcn.h>

@protocol ICBPrivateActivityCenter
- (instancetype)init;
- (id)observeDescriptorsWithHandler:(id)handler;
@end

id ICBCreateActivityCenter(void) {
    dlopen("/System/Library/Frameworks/ActivityKit.framework/ActivityKit",RTLD_NOW);
    Class cls=NSClassFromString(@"ACActivityCenter");
    Method initializer=class_getInstanceMethod(cls,sel_registerName("init"));
    if(!initializer||strcmp(method_getTypeEncoding(initializer),"@16@0:8")!=0)return nil;
    return [[cls alloc] init];
}

id ICBReadActivityCenterBridge(id center) {
    Ivar variable=class_getInstanceVariable(object_getClass(center),"_activityCenter");
    const char *type=variable ? ivar_getTypeEncoding(variable) : NULL;
    if(!type||type[0]!='@')return nil;
    return object_getIvar(center,variable);
}

id ICBObserveActivities(id center,void (^callback)(void)) {
    Method method=class_getInstanceMethod(object_getClass(center),sel_registerName("observeDescriptorsWithHandler:"));
    if(!method||strcmp(method_getTypeEncoding(method),"@24@0:8@?16")!=0)return nil;
    // The callback is notification-only: it consumes no unverified payload arguments.
    return [(id<ICBPrivateActivityCenter>)center observeDescriptorsWithHandler:[callback copy]];
}

id ICBDescribeObject(id object) {
    NSMutableArray *hierarchy=[NSMutableArray new];
    for(Class cls=object_getClass(object);cls&&hierarchy.count<5;cls=class_getSuperclass(cls)) {
        NSMutableArray *methods=[NSMutableArray new],*variables=[NSMutableArray new];
        unsigned count=0;Method *list=class_copyMethodList(cls,&count);
        for(unsigned i=0;i<count&&i<150;i++) {
            const char *types=method_getTypeEncoding(list[i]);
            [methods addObject:@{@"selector":NSStringFromSelector(method_getName(list[i])),@"types":types ? @(types) : @"unknown"}];
        }
        free(list);
        Ivar *ivars=class_copyIvarList(cls,&count);
        for(unsigned i=0;i<count&&i<50;i++) {
            const char *name=ivar_getName(ivars[i]),*type=ivar_getTypeEncoding(ivars[i]);
            [variables addObject:@{@"name":name ? @(name) : @"unknown",@"type":type ? @(type) : @"unknown"}];
        }
        free(ivars);
        [hierarchy addObject:@{@"class":NSStringFromClass(cls),@"methods":methods,@"ivars":variables}];
        if(cls==NSObject.class)break;
    }
    return hierarchy;
}

BOOL ICBInvalidateObserver(id token) {
    SEL selector=sel_registerName("invalidate");
    Method method=class_getInstanceMethod(object_getClass(token),selector);
    if(!method||strcmp(method_getTypeEncoding(method),"v16@0:8")!=0)return NO;
    ((void(*)(id,SEL))objc_msgSend)(token,selector);
    return YES;
}

@protocol ICBBoardServiceConnection
- (id)remoteTarget;
- (id)remoteProcess;
- (id)service;
@end
@protocol ICBActivityOutputServer
- (id)activityDescriptorContentStatesWithError:(NSError **)error;
- (id)activityDescriptorForIdentifier:(NSString *)identifier;
- (id)subscribeWithOptions:(id)options error:(NSError **)error;
@end

static id Summary(id value,unsigned depth) {
    if(!value)return NSNull.null;
    NSMutableDictionary *result=[@{@"class":NSStringFromClass(object_getClass(value))} mutableCopy];
    if([value isKindOfClass:NSData.class]) {
        result[@"bytes"]=@([value length]);
        const unsigned char *bytes=[value bytes];NSMutableString *magic=[NSMutableString new];
        for(NSUInteger i=0;i<MIN((NSUInteger)8,[value length]);i++)[magic appendFormat:@"%02x",bytes[i]];
        result[@"prefix_hex"]=magic;
        if([value length]<=262144&&depth<5) {
            id json=[NSJSONSerialization JSONObjectWithData:value options:NSJSONReadingFragmentsAllowed error:nil];
            if(json)result[@"json_structure"]=Summary(json,depth+1);
            id plist=[NSPropertyListSerialization propertyListWithData:value options:NSPropertyListImmutable format:nil error:nil];
            if(plist)result[@"plist_structure"]=Summary(plist,depth+1);
        }
    } else if([value isKindOfClass:NSDictionary.class]) {
        result[@"count"]=@([value count]);
        if(depth<5) {
            NSMutableDictionary *children=[NSMutableDictionary new];unsigned count=0;
            for(id key in value) {
                if(count++>=30)break;
                if([key isKindOfClass:NSString.class]&&[key length]<180)children[key]=Summary(value[key],depth+1);
            }
            result[@"children"]=children;
        }
    } else if([value isKindOfClass:NSArray.class]) {
        result[@"count"]=@([value count]);
        if(depth<5) {
            NSMutableArray *children=[NSMutableArray new];
            for(id child in value) {if(children.count>=6)break;[children addObject:Summary(child,depth+1)];}
            result[@"children"]=children;
        }
    }
    return result;
}

static id DecodeContainer(id value) {
    if(![value isKindOfClass:NSData.class]||[value length]>262144)return value;
    id parsed=[NSJSONSerialization JSONObjectWithData:value options:NSJSONReadingFragmentsAllowed error:nil];
    if(!parsed)parsed=[NSPropertyListSerialization propertyListWithData:value options:NSPropertyListImmutable format:nil error:nil];
    return parsed ?: value;
}

static id TargetJSONValue(id value,unsigned depth,unsigned *remaining,BOOL *truncated) {
    if(!value)return NSNull.null;
    if(depth>14||!*remaining){*truncated=YES;return @{@"truncated":@YES};}
    --*remaining;
    if([value isKindOfClass:NSData.class]) {
        NSUInteger length=[value length];
        if(length>262144){*truncated=YES;return @{@"encoding":@"binary",@"byte_count":@(length),@"truncated":@YES};}
        id decoded=[NSJSONSerialization JSONObjectWithData:value options:NSJSONReadingFragmentsAllowed error:nil];
        NSString *format=decoded ? @"json" : @"property-list";
        if(!decoded)decoded=[NSPropertyListSerialization propertyListWithData:value options:NSPropertyListImmutable format:nil error:nil];
        if(decoded)return @{@"encoding":@"decoded-data",@"format":format,@"byte_count":@(length),@"decoded":TargetJSONValue(decoded,depth+1,remaining,truncated)};
        return @{@"encoding":@"base64",@"byte_count":@(length),@"value":[value base64EncodedStringWithOptions:0]};
    }
    if([value isKindOfClass:NSString.class]){if([value length]<=8192)return value;*truncated=YES;return @{@"truncated":@YES,@"characters":@([value length])};}
    if([value isKindOfClass:NSNumber.class]||value==NSNull.null)return value;
    if([value isKindOfClass:NSDate.class])return [[NSISO8601DateFormatter new] stringFromDate:value];
    if([value isKindOfClass:NSDictionary.class]) {
        NSMutableDictionary *output=[NSMutableDictionary new];unsigned count=0;
        for(id key in value) {
            if(count++>=128){*truncated=YES;output[@"_truncated"]=@YES;break;}
            if([key isKindOfClass:NSString.class]&&[key length]<=512)output[key]=TargetJSONValue(value[key],depth+1,remaining,truncated);
            else *truncated=YES;
        }
        return output;
    }
    if([value isKindOfClass:NSArray.class]) {
        NSMutableArray *output=[NSMutableArray new];
        for(id item in value){if(output.count>=128){*truncated=YES;[output addObject:@{@"truncated":@YES}];break;}[output addObject:TargetJSONValue(item,depth+1,remaining,truncated)];}
        return output;
    }
    return @{@"unsupported_class":NSStringFromClass(object_getClass(value))};
}

id ICBQueryActivityOutput(id connection,NSString *identifier,BOOL includePayloads) {
    NSMutableDictionary *result=[@{@"source":@"ActivityKit-output-BSServiceConnection",@"target_activity_id":identifier} mutableCopy];
    Method getter=class_getInstanceMethod(object_getClass(connection),sel_registerName("remoteTarget"));
    if(!getter||strcmp(method_getTypeEncoding(getter),"@16@0:8")!=0) {result[@"status"]=@"unsupported_connection_abi";return result;}
    Protocol *protocol=objc_getProtocol("ACActivityOutputXPCServer");
    struct objc_method_description method=protocol_getMethodDescription(protocol,sel_registerName("activityDescriptorContentStatesWithError:"),YES,YES);
    if(!method.types||strcmp(method.types,"@24@0:8o^@16")!=0) {result[@"status"]=@"unsupported_protocol_abi";return result;}
    @try {
        for(NSString *name in @[@"remoteProcess",@"service"]) {
            SEL selector=NSSelectorFromString(name);Method read=class_getInstanceMethod(object_getClass(connection),selector);
            if(read&&strcmp(method_getTypeEncoding(read),"@16@0:8")==0) {
                id value=((id(*)(id,SEL))objc_msgSend)(connection,selector);
                result[name]=value ? [value description] : @"nil";
            }
        }
        id target=[(id<ICBBoardServiceConnection>)connection remoteTarget];
        result[@"proxy_class"]=target ? NSStringFromClass(object_getClass(target)) : @"nil";
        if(includePayloads) {
            struct objc_method_description subscribe=protocol_getMethodDescription(protocol,sel_registerName("subscribeWithOptions:error:"),YES,YES);
            if(!subscribe.types||strcmp(subscribe.types,"@32@0:8@16o^@24")!=0) {result[@"status"]=@"unsupported_subscribe_abi";return result;}
            NSData *options=[NSPropertyListSerialization dataWithPropertyList:@{@"includePayloads":@YES} format:NSPropertyListBinaryFormat_v1_0 options:0 error:nil];
            NSError *subscribeError=nil;
            id subscribed=[(id<ICBActivityOutputServer>)target subscribeWithOptions:options error:&subscribeError];
            result[@"subscription_structure"]=Summary(subscribed,0);
            if(subscribeError)result[@"subscription_error"]=@{@"domain":subscribeError.domain,@"code":@(subscribeError.code),@"description":subscribeError.localizedDescription};
        }
        NSError *error=nil;
        id states=[(id<ICBActivityOutputServer>)target activityDescriptorContentStatesWithError:&error];
        result[@"return_structure"]=Summary(states,0);
        result[@"status"]=error ? @"server_error" : states ? @"returned" : @"empty_return";
        if(error)result[@"error"]=@{@"domain":error.domain,@"code":@(error.code),@"description":error.localizedDescription};
        unsigned budget=0;id own=nil;
        id decoded=DecodeContainer(states);
        result[@"complete_for_service_response"]=@NO;
        if([decoded isKindOfClass:NSDictionary.class]&&[decoded[@"descriptorContentStates"] isKindOfClass:NSArray.class]) {
            result[@"complete_for_service_response"]=@YES;
            result[@"service_entry_count"]=@([decoded[@"descriptorContentStates"] count]);
            for(id entry in decoded[@"descriptorContentStates"]) {
                if(![entry isKindOfClass:NSDictionary.class])continue;
                id descriptor=entry[@"descriptor"];
                if(![descriptor isKindOfClass:NSDictionary.class])continue;
                id entryID=descriptor[@"id"];
                if([entryID isKindOfClass:NSString.class]&&[entryID isEqualToString:identifier]){own=entry;break;}
            }
        }
        result[@"target_found"]=@(own!=nil);
        if(own) {budget=1200;BOOL truncated=NO;result[@"target_activity_result"]=TargetJSONValue(own,0,&budget,&truncated);result[@"target_truncated"]=@(truncated);}
        id descriptor=[(id<ICBActivityOutputServer>)target activityDescriptorForIdentifier:identifier];
        result[@"target_descriptor_structure"]=Summary(descriptor,0);
    } @catch(NSException *exception) {
        result[@"status"]=@"exception";result[@"exception"]=exception.reason ?: exception.name;
    }
    return result;
}
