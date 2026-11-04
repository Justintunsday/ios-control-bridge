#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <objc/message.h>
#import <objc/runtime.h>
#import <stdio.h>
#import <stdlib.h>
#import <string.h>

/*
 * Fixed-purpose URL opener for `browser.open`.
 *
 * Calls LSApplicationWorkspace -openURL:withOptions:error: (or -openURL:).
 * This is a device-side UI action; the result records whether LaunchServices
 * accepted the request. The launched application itself is not inspected.
 */

static NSString *const BROWSER_SCHEMA = @"ios-control-bridge.browser.v1";
static NSString *const BROWSER_SOURCE = @"LSApplicationWorkspace";

static int emit(NSDictionary *payload) {
    NSError *error = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:payload options:0 error:&error];
    if (!data) {
        fprintf(stdout, "{\"schema\":\"%s\",\"status\":\"error\",\"reason\":\"json_encoding_failed\"}\n",
                [BROWSER_SCHEMA UTF8String]);
        return 4;
    }
    fwrite(data.bytes, 1, data.length, stdout);
    fputc('\n', stdout);
    fflush(stdout);
    NSString *status = payload[@"status"];
    if ([status isEqualToString:@"verified"]) {
        return 0;
    }
    if ([status isEqualToString:@"partial"]) {
        return 2;
    }
    if ([status isEqualToString:@"unavailable"]) {
        return 3;
    }
    return 4;
}

static NSDictionary *response(NSString *status, NSString *reason, NSDictionary *details) {
    NSMutableDictionary *payload = [NSMutableDictionary dictionary];
    payload[@"schema"] = BROWSER_SCHEMA;
    payload[@"status"] = status;
    payload[@"source"] = BROWSER_SOURCE;
    payload[@"observed_at_unix"] = @((double)time(NULL));
    if (reason) {
        payload[@"reason"] = reason;
    }
    if (details) {
        [payload addEntriesFromDictionary:details];
    }
    return payload;
}

static BOOL valid_url(NSString *url) {
    if (url.length < 8 || url.length > 4096) {
        return NO;
    }
    NSURL *parsed = [NSURL URLWithString:url];
    NSString *scheme = parsed.scheme.lowercaseString;
    return parsed && (([scheme isEqualToString:@"http"]) || ([scheme isEqualToString:@"https"]));
}

static BOOL open_url(NSString *url, NSError **error) {
    Class workspace_class = NSClassFromString(@"LSApplicationWorkspace");
    if (!workspace_class) {
        return NO;
    }
    SEL default_selector = sel_registerName("defaultWorkspace");
    id workspace = ((id (*)(id, SEL))objc_msgSend)((id)workspace_class, default_selector);
    if (!workspace) {
        return NO;
    }
    NSURL *parsed = [NSURL URLWithString:url];
    SEL selector = sel_registerName("openURL:withOptions:error:");
    if ([workspace respondsToSelector:selector]) {
        return ((BOOL (*)(id, SEL, id, id, NSError **))objc_msgSend)(
            workspace, selector, parsed, @{}, error);
    }
    selector = sel_registerName("openURL:");
    if ([workspace respondsToSelector:selector]) {
        return ((BOOL (*)(id, SEL, id))objc_msgSend)(workspace, selector, parsed);
    }
    return NO;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        if (argc != 2) {
            fprintf(stderr, "usage: icb-open-url <http(s)://...>\n");
            return emit(response(@"error", @"usage", nil));
        }
        NSString *url = [NSString stringWithUTF8String:argv[1]];
        if (!valid_url(url)) {
            return emit(response(@"error", @"invalid_url", @{@"url": url ?: @""}));
        }
        NSError *error = nil;
        BOOL opened = open_url(url, &error);
        NSMutableDictionary *details = [@{@"url": url, @"opened": @(opened)} mutableCopy];
        if (error) {
            details[@"error"] = error.localizedDescription ?: @"unknown error";
        }
        if (!opened) {
            return emit(response(@"unavailable", @"open_failed", details));
        }
        return emit(response(@"verified", nil, details));
    }
}
