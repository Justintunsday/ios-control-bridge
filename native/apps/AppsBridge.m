#import <Foundation/Foundation.h>
#import <objc/message.h>
#import <objc/runtime.h>
#import <dlfcn.h>
#import <stdio.h>
#import <string.h>
#import <unistd.h>
#import <pwd.h>
#import <grp.h>
#import <spawn.h>
#import <fcntl.h>
#import <signal.h>
#import <sys/wait.h>
#import <errno.h>

/* Fixed operations only. Method signatures are checked before every private call.
 * The installation selectors below were observed on 16.1.1 / 20B101.
 * Store offers come unchanged from Apple's lookup service, never fabricated.
 */
static NSString *command;
static NSDictionary *arguments;

static BOOL signature(id target, NSString *name, const char *returns, NSArray *types) {
    SEL selector = NSSelectorFromString(name);
    if (!target || ![target respondsToSelector:selector]) return NO;
    NSMethodSignature *s = [target methodSignatureForSelector:selector];
    if (!s || strcmp(s.methodReturnType, returns) || s.numberOfArguments != types.count + 2) return NO;
    for (NSUInteger i = 0; i < types.count; i++)
        if (strcmp([s getArgumentTypeAtIndex:i + 2], [types[i] UTF8String])) return NO;
    return YES;
}
static id object0(id target, NSString *name) {
    if (!signature(target, name, "@", @[])) return nil;
    return ((id (*)(id, SEL))objc_msgSend)(target, NSSelectorFromString(name));
}
static id object1(id target, NSString *name, id arg) {
    if (!signature(target, name, "@", @[@"@"])) return nil;
    return ((id (*)(id, SEL, id))objc_msgSend)(target, NSSelectorFromString(name), arg);
}
static BOOL boolean(id target, NSString *name) {
    if (!signature(target, name, "B", @[])) return NO;
    return ((BOOL (*)(id, SEL))objc_msgSend)(target, NSSelectorFromString(name));
}
static NSString *text(id value) {
    return [value isKindOfClass:NSString.class] && [value length] <= 1024 ? value : @"";
}
static BOOL validBundle(id value) {
    if (![value isKindOfClass:NSString.class] || [value length] > 255) return NO;
    return [value rangeOfString:@"^[A-Za-z0-9-]+(\\.[A-Za-z0-9-]+)+$" options:NSRegularExpressionSearch].location != NSNotFound;
}
static BOOL containerPath(NSString *path) {
    NSString *resolved = [path stringByResolvingSymlinksInPath];
    return [resolved hasPrefix:@"/private/var/containers/Bundle/Application/"] ||
           [resolved hasPrefix:@"/var/containers/Bundle/Application/"];
}
static NSMutableDictionary *response(NSString *status, NSString *reason) {
    NSMutableDictionary *out = [@{@"schema": @"ios-control-bridge.apps.v1", @"source": @"LaunchServices+StoreServices",
        @"command": command ?: @"", @"status": status, @"observed_at_unix": @([NSDate timeIntervalSinceReferenceDate] + NSTimeIntervalSince1970)} mutableCopy];
    if (reason) out[@"reason"] = reason;
    for (NSString *key in @[@"bundle_id", @"app_id"]) if (arguments[key]) out[key] = arguments[key];
    return out;
}
static int emit(NSDictionary *out) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:out options:0 error:NULL];
    if (!data) return 4;
    fwrite(data.bytes, 1, data.length, stdout); fputc('\n', stdout); fflush(stdout);
    return [@{@"verified": @0, @"partial": @2, @"unavailable": @3, @"error": @4}[out[@"status"]] intValue];
}
static NSDictionary *errorChain(NSError *error, NSUInteger depth) {
    if (!error) return @{};
    NSMutableDictionary *out = [@{@"domain": text(error.domain), @"code": @(error.code)} mutableCopy];
    id underlying = error.userInfo[NSUnderlyingErrorKey];
    if (depth < 3 && [underlying isKindOfClass:NSError.class]) out[@"underlying"] = errorChain(underlying, depth+1);
    return out;
}
static NSDictionary *errorDetails(NSError *error) {
    return errorChain(error, 0);
}
/* SSRequestDelegate / SSPurchaseRequestDelegate encodings were observed on
 * 20B101: v@:@, v@:@@ and v@:@@@. No purchase/account payload is exported. */
@interface ICBStoreObserver : NSObject
@property(atomic) BOOL completed;
@property(atomic) BOOL failed;
@property(atomic, strong) NSError *failure;
@end
@implementation ICBStoreObserver
- (void)requestDidFinish:(id)request { (void)request; self.completed = YES; }
- (void)request:(id)request didFailWithError:(NSError *)error {
    (void)request; self.failed = YES; self.failure = [error isKindOfClass:NSError.class] ? error : nil; self.completed = YES;
}
- (void)purchaseRequest:(id)request purchaseDidFail:(id)purchase withError:(NSError *)error {
    (void)purchase; [self request:request didFailWithError:error];
}
- (void)purchaseRequest:(id)request purchaseDidSucceed:(id)purchase {
    (void)purchase; [self requestDidFinish:request];
}
@end
static id workspace(void) {
    return object0(NSClassFromString(@"LSApplicationWorkspace"), @"defaultWorkspace");
}
static NSDictionary *appState(NSString *bundle, NSString **failure) {
    id ws = workspace();
    if (!signature(ws, @"applicationIsInstalled:", "B", @[@"@"])) { *failure = @"application_state_signature_unavailable"; return nil; }
    BOOL installed = ((BOOL (*)(id, SEL, id))objc_msgSend)(ws, NSSelectorFromString(@"applicationIsInstalled:"), bundle);
    id proxy = object1(NSClassFromString(@"LSApplicationProxy"), @"applicationProxyForIdentifier:", bundle);
    if (installed && (!proxy || !signature(proxy, @"isInstalled", "B", @[]) ||
                      !signature(proxy, @"isPlaceholder", "B", @[]) || !signature(proxy, @"bundleURL", "@", @[]))) {
        *failure = @"application_proxy_unavailable"; return nil;
    }
    if (installed && ![object0(proxy, @"bundleIdentifier") isEqual:bundle]) { *failure = @"application_identity_mismatch"; return nil; }
    BOOL placeholder = boolean(proxy, @"isPlaceholder");
    if (installed && !boolean(proxy, @"isInstalled") && !placeholder) { *failure = @"application_state_inconsistent"; return nil; }
    id url = object0(proxy, @"bundleURL");
    NSString *path = [url isKindOfClass:NSURL.class] ? [url path] : @"";
    BOOL protected = [bundle hasPrefix:@"com.apple."] || ((installed || placeholder) && !containerPath(path));
    return @{@"bundle_id": bundle, @"installed": @(installed), @"placeholder": @(placeholder),
             @"protected": @(protected), @"name": text(object0(proxy, @"localizedName")),
             @"version": text(object0(proxy, @"bundleVersion")), @"application_type": text(object0(proxy, @"applicationType"))};
}
static NSDictionary *getApp(void) {
    NSString *failure = nil;
    NSDictionary *app = appState(arguments[@"bundle_id"], &failure);
    NSMutableDictionary *out = response(app ? @"verified" : @"unavailable", failure);
    if (app) out[@"app"] = app;
    return out;
}
static NSDictionary *listApps(void) {
    id applications = object0(workspace(), @"allInstalledApplications");
    if (![applications isKindOfClass:NSArray.class]) return response(@"unavailable", @"application_list_unavailable");
    NSMutableArray *rows = [NSMutableArray array];
    NSString *query = [text(arguments[@"query"]) lowercaseString];
    for (id proxy in applications) {
        NSString *bundle = object0(proxy, @"bundleIdentifier");
        if (!validBundle(bundle)) continue;
        NSString *failure = nil;
        NSDictionary *app = appState(bundle, &failure);
        if (!app) return response(@"partial", failure);
        if (!app[@"installed"] || ![app[@"installed"] boolValue]) continue;
        if (![arguments[@"include_system"] boolValue] && [app[@"protected"] boolValue]) continue;
        if (query.length && ![[bundle lowercaseString] containsString:query] && ![[app[@"name"] lowercaseString] containsString:query]) continue;
        [rows addObject:app];
    }
    [rows sortUsingComparator:^NSComparisonResult(NSDictionary *a, NSDictionary *b) { return [a[@"bundle_id"] compare:b[@"bundle_id"]]; }];
    NSUInteger offset = [arguments[@"offset"] unsignedIntegerValue], limit = [arguments[@"limit"] unsignedIntegerValue];
    if (offset > 100000 || limit < 1 || limit > 500) return response(@"error", @"invalid_pagination");
    NSUInteger start = MIN(offset, rows.count), count = MIN(limit, rows.count - start);
    NSMutableDictionary *out = response(@"verified", nil);
    out[@"apps"] = [rows subarrayWithRange:NSMakeRange(start, count)];
    out[@"has_more"] = @((BOOL)(start + count < rows.count)); out[@"total"] = @(rows.count); out[@"offset"] = @(offset);
    return out;
}
static NSDictionary *trollStore(BOOL install) {
    if (getuid() != 0) return response(@"unavailable", @"trollstore_requires_root");
    id proxy = object1(NSClassFromString(@"LSApplicationProxy"), @"applicationProxyForIdentifier:", @"com.opa334.TrollStore");
    id url = object0(proxy, @"bundleURL");
    NSString *path = [url isKindOfClass:NSURL.class] ? [url path] : @"";
    NSString *helper = [path stringByAppendingPathComponent:@"trollstorehelper"];
    if (![object0(proxy, @"bundleIdentifier") isEqual:@"com.opa334.TrollStore"] || !boolean(proxy, @"isInstalled") ||
        !containerPath(path) || ![path.pathExtension isEqual:@"app"] || ![[NSFileManager defaultManager] isExecutableFileAtPath:helper])
        return response(@"unavailable", @"existing_trollstore_helper_missing");
    NSMutableArray *args = [NSMutableArray arrayWithObjects:helper, install ? @"install" : @"uninstall", nil];
    if (install && [arguments[@"replace"] boolValue]) [args addObject:@"force"];
    [args addObject:install ? arguments[@"path"] : arguments[@"bundle_id"]];
    char *argv[5] = {0};
    for (NSUInteger i = 0; i < args.count; i++) argv[i] = (char *)[args[i] UTF8String];
    posix_spawn_file_actions_t actions; posix_spawn_file_actions_init(&actions);
    posix_spawn_file_actions_addopen(&actions, STDIN_FILENO, "/dev/null", O_RDONLY, 0);
    posix_spawn_file_actions_addopen(&actions, STDOUT_FILENO, "/dev/null", O_WRONLY, 0);
    posix_spawn_file_actions_addopen(&actions, STDERR_FILENO, "/dev/null", O_WRONLY, 0);
    posix_spawnattr_t attr; posix_spawnattr_init(&attr);
    posix_spawnattr_setflags(&attr, POSIX_SPAWN_SETPGROUP); posix_spawnattr_setpgroup(&attr, 0);
    char *env[] = {"PATH=/var/jb/usr/bin:/var/jb/bin:/usr/bin:/bin", NULL};
    pid_t pid = 0; int spawnError = posix_spawn(&pid, helper.UTF8String, &actions, &attr, argv, env);
    posix_spawn_file_actions_destroy(&actions); posix_spawnattr_destroy(&attr);
    if (spawnError) return response(@"unavailable", @"trollstore_process_unavailable");
    int status = 0; pid_t waited = 0;
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:60];
    do {
        waited = waitpid(pid, &status, WNOHANG);
        if (waited == pid || (waited < 0 && errno != EINTR)) break;
        usleep(50000);
    } while (deadline.timeIntervalSinceNow > 0);
    if (waited != pid) {
        kill(-pid, SIGKILL); waitpid(pid, &status, 0);
        NSMutableDictionary *out = response(@"partial", @"trollstore_timeout_outcome_unknown");
        out[@"outcome_unknown"] = @YES; out[@"installer"] = @"trollstore"; return out;
    }
    BOOL accepted = WIFEXITED(status) && WEXITSTATUS(status) == 0;
    NSMutableDictionary *out = response(accepted ? @"partial" : @"unavailable", accepted ? @"request_accepted_readback_required" : @"trollstore_request_refused");
    out[@"accepted"] = @(accepted); out[@"installer"] = @"trollstore";
    out[@"installer_exit"] = @(WIFEXITED(status) ? WEXITSTATUS(status) : -1);
    return out;
}
static NSDictionary *changeApp(BOOL install) {
    NSString *bundle = arguments[@"bundle_id"], *failure = nil;
    NSDictionary *before = appState(bundle, &failure);
    if (!before) return response(@"unavailable", failure);
    if ([before[@"protected"] boolValue]) return response(@"error", @"protected_app");
    if (install && [before[@"installed"] boolValue] && ![arguments[@"replace"] boolValue]) return response(@"error", @"app_already_installed");
    if (!install && ![before[@"installed"] boolValue] && ![before[@"placeholder"] boolValue]) {
        NSMutableDictionary *out = response(@"partial", @"already_absent_readback_required");
        out[@"accepted"] = @YES; return out;
    }
    NSString *installer = arguments[@"installer"] ?: @"system";
    if (![installer isEqual:@"system"] && ![installer isEqual:@"trollstore"]) return response(@"error", @"invalid_installer");
    if ([installer isEqual:@"trollstore"]) {
        if (install && ![text(arguments[@"path"]) isAbsolutePath]) return response(@"error", @"ipa_file_unavailable");
        return trollStore(install);
    }
    id ws = workspace(); NSError *error = nil; BOOL accepted = NO;
    if (install) {
        NSString *path = text(arguments[@"path"]);
        if (![path isAbsolutePath] || ![[NSFileManager defaultManager] fileExistsAtPath:path]) return response(@"error", @"ipa_file_unavailable");
        NSString *selector = @"installApplication:withOptions:error:";
        if (!signature(ws, selector, "B", @[@"@", @"@", @"^@"])) return response(@"unavailable", @"install_signature_unavailable");
        accepted = ((BOOL (*)(id, SEL, id, id, NSError **))objc_msgSend)(ws, NSSelectorFromString(selector),
            [NSURL fileURLWithPath:path], @{@"CFBundleIdentifier": bundle}, &error);
    } else {
        NSString *selector = @"uninstallApplication:withOptions:error:usingBlock:";
        if (!signature(ws, selector, "B", @[@"@", @"@", @"^@", @"@?"])) return response(@"unavailable", @"uninstall_signature_unavailable");
        accepted = ((BOOL (*)(id, SEL, id, id, NSError **, id))objc_msgSend)(ws, NSSelectorFromString(selector), bundle, @{}, &error, nil);
    }
    NSMutableDictionary *out = response(accepted ? @"partial" : @"unavailable", accepted ? @"request_accepted_readback_required" : @"system_request_refused");
    out[@"accepted"] = @(accepted); if (error) out[@"system_error"] = errorDetails(error);
    return out;
}

static void waitFor(BOOL (^finished)(void), NSTimeInterval seconds) {
    NSDate *end = [NSDate dateWithTimeIntervalSinceNow:seconds];
    while (!finished() && end.timeIntervalSinceNow > 0)
        [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
}
/* Returns only the requested catalog item; no account/purchase-history output. */
static id lookup(NSString *appID, NSString **failure, NSError **error) {
    __attribute__((objc_precise_lifetime)) id request = [[NSClassFromString(@"SSLookupRequest") alloc] init];
    if (!signature(request, @"setValue:forRequestParameter:", "v", @[@"@", @"@"]) ||
        !signature(request, @"startWithLookupBlock:", "v", @[@"@?"]) ||
        !signature(request, @"setKeyProfile:", "v", @[@"@"]) ||
        !signature(request, @"setAuthenticatesIfNeeded:", "v", @[@"B"])) {
        *failure = @"store_lookup_signature_unavailable"; return nil;
    }
    ((void (*)(id, SEL, BOOL))objc_msgSend)(request, NSSelectorFromString(@"setAuthenticatesIfNeeded:"), NO);
    ((void (*)(id, SEL, id))objc_msgSend)(request, NSSelectorFromString(@"setKeyProfile:"), @"product");
    ((void (*)(id, SEL, id, id))objc_msgSend)(request, NSSelectorFromString(@"setValue:forRequestParameter:"), appID, @"id");
    __block id reply = nil; __block NSError *lookupError = nil; __block BOOL done = NO;
    NSObject *lock = [NSObject new];
    void (^callback)(id, NSError *) = ^(id response, NSError *err) { @synchronized(lock) { reply = response; lookupError = err; done = YES; } };
    ((void (*)(id, SEL, id))objc_msgSend)(request, NSSelectorFromString(@"startWithLookupBlock:"), callback);
    waitFor(^BOOL { @synchronized(lock) { return done; } }, 20);
    @synchronized(lock) {
        if (!done) { *failure = @"store_lookup_timeout"; return nil; }
        if (lookupError) { *failure = @"store_lookup_failed"; *error = lookupError; return nil; }
        id items = object0(reply, @"allItems");
        if (![items isKindOfClass:NSArray.class]) { *failure = @"store_lookup_items_unavailable"; return nil; }
        for (id item in items) {
            id identifier = object0(item, @"ITunesStoreIdentifier");
            if ([[identifier description] isEqual:appID]) return item;
        }
    }
    *failure = @"app_store_item_not_found"; return nil;
}
static id freeOffer(id item) {
    id offers = object0(item, @"offers");
    if (![offers isKindOfClass:NSArray.class]) return nil;
    for (id offer in offers) {
        id price = object0(offer, @"price");
        NSString *buy = object0(offer, @"buyParameters");
        if (![price isKindOfClass:NSNumber.class] || [price doubleValue] != 0 || ![buy isKindOfClass:NSString.class] || !buy.length) continue;
        // Subscription/trial offers are not app downloads.
        NSString *subscription = object0(offer, @"subscriptionType");
        if ([subscription isKindOfClass:NSString.class] && subscription.length) continue;
        return offer;
    }
    return nil;
}
static NSDictionary *store(BOOL download) {
    NSString *failure = nil; NSError *error = nil;
    id item = lookup(arguments[@"app_id"], &failure, &error);
    if (!item) {
        NSMutableDictionary *out = response(@"unavailable", failure);
        if (error) out[@"system_error"] = errorDetails(error);
        return out;
    }
    NSString *bundle = object0(item, @"bundleIdentifier");
    NSString *kind = object0(item, @"itemKind");
    if (!validBundle(bundle) || !([kind isEqual:@"software"] || [kind isEqual:@"iosSoftware"])) return response(@"unavailable", @"app_store_software_metadata_required");
    id offer = freeOffer(item);
    NSDictionary *app = @{@"app_id": arguments[@"app_id"], @"bundle_id": bundle, @"name": text(object0(item, @"displayName")), @"free_offer": @((BOOL)(offer != nil))};
    if (!download) { NSMutableDictionary *out = response(@"verified", nil); out[@"app"] = app; return out; }
    if (![bundle isEqual:arguments[@"bundle_id"]]) return response(@"error", @"app_store_bundle_id_mismatch");
    if (!offer) return response(@"unavailable", @"free_offer_required");
    NSDictionary *before = appState(bundle, &failure);
    if (!before) return response(@"unavailable", failure);
    if ([before[@"protected"] boolValue]) return response(@"error", @"protected_app");
    if ([before[@"installed"] boolValue] && ![before[@"placeholder"] boolValue]) return response(@"partial", @"already_installed_readback_required");
    if ([before[@"placeholder"] boolValue]) return response(@"partial", @"store_download_pending");
    NSString *buyParameters = object0(offer, @"buyParameters");
    if (![buyParameters isKindOfClass:NSString.class] || !buyParameters.length) return response(@"unavailable", @"store_offer_unavailable");
    __attribute__((objc_precise_lifetime)) id purchase = object1(NSClassFromString(@"SSPurchase"), @"purchaseWithBuyParameters:", buyParameters);
    __attribute__((objc_precise_lifetime)) id request = object1([NSClassFromString(@"SSPurchaseRequest") alloc], @"initWithPurchases:", purchase ? @[purchase] : @[]);
    if (!purchase || !request || !signature(purchase, @"setCreatesDownloads:", "v", @[@"B"]) ||
        !signature(purchase, @"setCreatesInstallJobs:", "v", @[@"B"]) ||
        !signature(request, @"setCreatesDownloads:", "v", @[@"B"]) ||
        !signature(request, @"setShouldValidatePurchases:", "v", @[@"B"]) ||
        !signature(request, @"setDelegate:", "v", @[@"@"]) ||
        !signature(request, @"cancel", "v", @[]) ||
        !signature(request, @"start", "B", @[])) return response(@"unavailable", @"store_download_signature_unavailable");
    ((void (*)(id, SEL, BOOL))objc_msgSend)(purchase, NSSelectorFromString(@"setCreatesDownloads:"), YES);
    ((void (*)(id, SEL, BOOL))objc_msgSend)(purchase, NSSelectorFromString(@"setCreatesInstallJobs:"), YES);
    ((void (*)(id, SEL, BOOL))objc_msgSend)(request, NSSelectorFromString(@"setCreatesDownloads:"), YES);
    ((void (*)(id, SEL, BOOL))objc_msgSend)(request, NSSelectorFromString(@"setShouldValidatePurchases:"), YES);
    // The system retains its normal account/authentication checks and confirmation UI.
    __attribute__((objc_precise_lifetime)) ICBStoreObserver *observer = [ICBStoreObserver new];
    for (NSString *name in @[@"SSRequestDelegate", @"SSPurchaseRequestDelegate"]) {
        Protocol *protocol = NSProtocolFromString(name);
        if (!protocol) return response(@"unavailable", @"store_delegate_protocol_unavailable");
        class_addProtocol(ICBStoreObserver.class, protocol);
    }
    ((void (*)(id, SEL, id))objc_msgSend)(request, NSSelectorFromString(@"setDelegate:"), observer);
    BOOL started = ((BOOL (*)(id, SEL))objc_msgSend)(request, NSSelectorFromString(@"start"));
    if (!started) return response(@"unavailable", @"store_request_not_started");
    NSMutableDictionary *out = response(@"partial", @"store_request_submitted_readback_required");
    out[@"submitted"] = @YES; out[@"app"] = app;
    out[@"worker_pid"] = @(getpid());
    out[@"worker_expires_at_unix"] = @([[NSDate date] timeIntervalSince1970] + 600);
    // A bounded background worker must retain the purchasing context through
    // device-side authentication. Returning from this process earlier can
    // cancel the transaction while the system confirmation is still visible.
    emit(out);
    waitFor(^BOOL { return observer.completed; }, 600);
    if (!observer.completed) ((void (*)(id, SEL))objc_msgSend)(request, NSSelectorFromString(@"cancel"));
    if (observer.completed) waitFor(^BOOL { return NO; }, 5);
    NSMutableDictionary *finished = response(observer.failed ? @"unavailable" : @"partial",
        observer.failed ? @"store_request_failed" : observer.completed ? @"store_request_finished_readback_required" : @"store_worker_expired");
    finished[@"callback_completed"] = @(observer.completed);
    if (observer.failure) finished[@"system_error"] = errorDetails(observer.failure);
    emit(finished);
    return nil;
}

#ifndef ICB_APPS_TESTING
int main(int argc, char **argv) {
    @autoreleasepool {
        if (argc != 3 || strlen(argv[2]) > 65536) return emit(response(@"error", @"usage"));
        command = @(argv[1]);
        NSData *data = [@(argv[2]) dataUsingEncoding:NSUTF8StringEncoding];
        arguments = [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL];
        if (![arguments isKindOfClass:NSDictionary.class]) { arguments = @{}; return emit(response(@"error", @"invalid_parameters")); }
        NSDictionary *version = [NSDictionary dictionaryWithContentsOfFile:@"/System/Library/CoreServices/SystemVersion.plist"];
        if (![version[@"ProductVersion"] isEqual:@"16.1.1"] || ![version[@"ProductBuildVersion"] isEqual:@"20B101"]) return emit(response(@"unavailable", @"unverified_os_build"));
        BOOL storeCommand = [command isEqual:@"store_info"] || [command isEqual:@"store_download"];
        if (storeCommand && getuid() == 0) {
            struct passwd *user = getpwnam("mobile");
            if (!user || initgroups(user->pw_name, user->pw_gid) || setgid(user->pw_gid) || setuid(user->pw_uid)) return emit(response(@"unavailable", @"mobile_store_context_unavailable"));
            setenv("HOME", user->pw_dir, 1);
        }
        for (NSString *image in @[@"/System/Library/Frameworks/CoreServices.framework/CoreServices", @"/System/Library/PrivateFrameworks/StoreServices.framework/StoreServices"])
            dlopen(image.UTF8String, RTLD_LAZY | RTLD_GLOBAL);
        @try {
            if (storeCommand) {
                if (![arguments[@"app_id"] isKindOfClass:NSString.class] || [arguments[@"app_id"] rangeOfString:@"^[1-9][0-9]{0,18}$" options:NSRegularExpressionSearch].location == NSNotFound) return emit(response(@"error", @"invalid_app_id"));
                if ([command isEqual:@"store_download"]) alarm(660);
                NSDictionary *out = store([command isEqual:@"store_download"]);
                return out ? emit(out) : 2;
            }
            if ([command isEqual:@"list"]) return emit(listApps());
            if (!validBundle(arguments[@"bundle_id"])) return emit(response(@"error", @"invalid_bundle_id"));
            if ([command isEqual:@"get"]) return emit(getApp());
            if ([command isEqual:@"install"]) return emit(changeApp(YES));
            if ([command isEqual:@"uninstall"]) return emit(changeApp(NO));
            return emit(response(@"error", @"unknown_command"));
        } @catch (NSException *exception) {
            (void)exception;
            // A write may have reached the system. Never suggest replaying it automatically.
            NSMutableDictionary *out = response(@"partial", @"native_exception_outcome_unknown");
            out[@"outcome_unknown"] = @YES; return emit(out);
        }
    }
}
#endif
