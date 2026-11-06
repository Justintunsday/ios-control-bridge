#import <Foundation/Foundation.h>
static NSString *mode;
static BOOL mutated;
@interface ICBAppProxy : NSObject
+ (id)applicationProxyForIdentifier:(id)identifier;
- (id)bundleIdentifier;
- (BOOL)isInstalled;
- (BOOL)isPlaceholder;
- (id)bundleURL;
- (id)bundleVersion;
@end
@implementation ICBAppProxy
+ (id)applicationProxyForIdentifier:(id)identifier { (void)identifier; return [self new]; }
- (id)bundleIdentifier { return @"dev.ioscontrol.appsfixture"; }
- (BOOL)isInstalled { return YES; }
- (BOOL)isPlaceholder { return NO; }
- (id)bundleURL { return [NSURL fileURLWithPath:[mode isEqual:@"protected"] ? @"/Applications/System.app" : @"/var/containers/Bundle/Application/fixture/Fixture.app"]; }
- (id)bundleVersion { return @"1"; }
@end
@interface ICBAppWorkspace : NSObject
+ (id)defaultWorkspace;
- (BOOL)applicationIsInstalled:(id)bundle;
- (BOOL)uninstallApplication:(id)bundle withOptions:(id)options error:(NSError **)error usingBlock:(void (^)(id))block;
@end
@implementation ICBAppWorkspace
+ (id)defaultWorkspace { return [self new]; }
- (BOOL)applicationIsInstalled:(id)bundle { (void)bundle; return YES; }
- (BOOL)uninstallApplication:(id)bundle withOptions:(id)options error:(NSError **)error usingBlock:(void (^)(id))block {
    (void)bundle; (void)options; (void)error; (void)block;
    mutated = YES; return ![mode isEqual:@"refused"];
}
@end
/* Deliberately incompatible error-pointer signature must never be called. */
@interface ICBWrongWorkspace : NSObject
+ (id)defaultWorkspace;
- (BOOL)applicationIsInstalled:(id)bundle;
- (BOOL)uninstallApplication:(id)bundle withOptions:(id)options error:(id)error usingBlock:(id)block;
@end
@implementation ICBWrongWorkspace
+ (id)defaultWorkspace { return [self new]; }
- (BOOL)applicationIsInstalled:(id)bundle { (void)bundle; return YES; }
- (BOOL)uninstallApplication:(id)b withOptions:(id)o error:(id)e usingBlock:(id)k { (void)b; (void)o; (void)e; (void)k; abort(); }
@end
static Class appFixtureClass(NSString *name) {
    if ([name isEqual:@"LSApplicationWorkspace"]) return [mode isEqual:@"signature"] ? ICBWrongWorkspace.class : ICBAppWorkspace.class;
    if ([name isEqual:@"LSApplicationProxy"]) return ICBAppProxy.class;
    return Nil;
}
#define ICB_APPS_TESTING 1
#define NSClassFromString appFixtureClass
#include "../../native/apps/AppsBridge.m"
#undef NSClassFromString
int main(int argc, char **argv) { @autoreleasepool {
    mode = argc > 1 ? @(argv[1]) : @"accepted";
    command = @"uninstall"; arguments = @{@"bundle_id": @"dev.ioscontrol.appsfixture"};
    if ([mode hasPrefix:@"delegate_"]) {
        ICBStoreObserver *observer = [ICBStoreObserver new];
        if ([mode isEqual:@"delegate_failure"]) {
            NSError *underlying = [NSError errorWithDomain:@"fixture.network" code:-1 userInfo:nil];
            [observer purchaseRequest:nil purchaseDidFail:nil withError:[NSError errorWithDomain:@"fixture.store" code:7 userInfo:@{NSUnderlyingErrorKey:underlying}]];
            if (!observer.completed || !observer.failed) return 99;
            NSMutableDictionary *out = response(@"unavailable", @"store_request_failed");
            out[@"system_error"] = errorDetails(observer.failure); return emit(out);
        }
        [observer purchaseRequest:nil purchaseDidSucceed:nil];
        if (!observer.completed || observer.failed) return 99;
        return emit(response(@"partial", @"store_request_finished_readback_required"));
    }
    NSDictionary *out = changeApp(NO);
    BOOL shouldMutate = [mode isEqual:@"accepted"] || [mode isEqual:@"refused"];
    if (mutated != shouldMutate) return 99;
    return emit(out);
}}
