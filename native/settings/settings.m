#import <Foundation/Foundation.h>
#import <AVFoundation/AVFoundation.h>
#import <math.h>
#import <objc/message.h>
#import <stdio.h>
#import <stdlib.h>
#import <string.h>
#import <unistd.h>

/*
 * Device-side adapter for settings that have no public app-context API.
 *
 * This helper performs one fixed, reversible operation per invocation:
 *   icb-settings get volume
 *   icb-settings set volume <0.0-1.0>
 *
 * The result is JSON on stdout. Exit status follows the project contract:
 * 0 = verified, 2 = partial, 3 = unavailable, 4 = error.
 */

static NSString *const SETTINGS_SCHEMA = @"ios-control-bridge.settings.v1";
static NSString *const SETTINGS_SOURCE = @"AVSystemController";
static NSString *const VOLUME_SETTING = @"volume";
static NSString *const VOLUME_CATEGORY = @"Audio/Video";
static const double VOLUME_TOLERANCE = 0.001;

static int emit(NSDictionary *payload) {
    NSError *error = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:payload options:0 error:&error];
    if (!data) {
        fprintf(stdout, "{\"schema\":\"%s\",\"status\":\"error\",\"reason\":\"json_encoding_failed\"}\n",
                [SETTINGS_SCHEMA UTF8String]);
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

static NSDictionary *response(NSString *status, NSDictionary *details) {
    NSMutableDictionary *payload = [NSMutableDictionary dictionary];
    payload[@"schema"] = SETTINGS_SCHEMA;
    payload[@"status"] = status;
    payload[@"setting"] = VOLUME_SETTING;
    payload[@"category"] = VOLUME_CATEGORY;
    payload[@"source"] = SETTINGS_SOURCE;
    payload[@"observed_at_unix"] = @((double)time(NULL));
    if (details) {
        [payload addEntriesFromDictionary:details];
    }
    return payload;
}

static NSDictionary *error_response(NSString *reason) {
    return response(@"error", @{@"reason": reason});
}

static id volume_controller(Class *controller_class) {
    Class cls = NSClassFromString(@"AVSystemController");
    if (!cls) {
        return nil;
    }
    *controller_class = cls;
    SEL selector = sel_registerName("sharedAVSystemController");
    return ((id (*)(id, SEL))objc_msgSend)((id)cls, selector);
}

static BOOL read_volume(id controller, float *value) {
    if (!controller || !value) {
        return NO;
    }
    SEL selector = sel_registerName("getVolume:forCategory:");
    return ((BOOL (*)(id, SEL, float *, id))objc_msgSend)(controller, selector, value, VOLUME_CATEGORY);
}

static BOOL write_volume(id controller, float value) {
    if (!controller) {
        return NO;
    }
    SEL selector = sel_registerName("setVolumeTo:forCategory:");
    return ((BOOL (*)(id, SEL, float, id))objc_msgSend)(controller, selector, value, VOLUME_CATEGORY);
}

static NSDictionary *get_volume(void) {
    Class controller_class = Nil;
    id controller = volume_controller(&controller_class);
    if (!controller) {
        return response(@"unavailable", @{@"reason": @"system_class_unavailable"});
    }
    float value = -1.0f;
    if (!read_volume(controller, &value)) {
        return error_response(@"read_failed");
    }
    return response(@"verified", @{
        @"value": @(value),
        @"range": @{@"min": @(0.0), @"max": @(1.0)},
        @"unit": @"fraction"
    });
}

static NSDictionary *set_volume(double requested) {
    Class controller_class = Nil;
    id controller = volume_controller(&controller_class);
    if (!controller) {
        return response(@"unavailable", @{@"reason": @"system_class_unavailable"});
    }
    float before = -1.0f;
    if (!read_volume(controller, &before)) {
        return error_response(@"read_before_failed");
    }
    if (!write_volume(controller, (float)requested)) {
        return error_response(@"write_failed");
    }
    usleep(200000);
    float readback = -1.0f;
    if (!read_volume(controller, &readback)) {
        return error_response(@"readback_failed");
    }
    double delta = (double)readback - requested;
    BOOL verified = fabs(delta) <= VOLUME_TOLERANCE;
    NSMutableDictionary *details = [@{
        @"before": @(before),
        @"requested": @(requested),
        @"readback": @(readback),
        @"delta": @(delta),
        @"tolerance": @(VOLUME_TOLERANCE),
        @"verified": @(verified),
        @"range": @{@"min": @(0.0), @"max": @(1.0)},
        @"unit": @"fraction"
    } mutableCopy];
    if (!verified) {
        details[@"reason"] = @"readback_mismatch";
    }
    return response(verified ? @"verified" : @"partial", details);
}

static BOOL parse_volume(const char *text, double *value) {
    if (!text || !value) {
        return NO;
    }
    char *end = NULL;
    double parsed = strtod(text, &end);
    if (end == text || (end && *end != '\0')) {
        return NO;
    }
    if (!isfinite(parsed) || parsed < 0.0 || parsed > 1.0) {
        return NO;
    }
    *value = parsed;
    return YES;
}

static int usage(void) {
    fprintf(stderr, "usage: icb-settings get volume\n");
    fprintf(stderr, "       icb-settings set volume <0.0-1.0>\n");
    return 4;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        if (argc < 3) {
            return usage();
        }
        NSString *command = [NSString stringWithUTF8String:argv[1]];
        NSString *setting = [NSString stringWithUTF8String:argv[2]];
        if (![setting isEqualToString:VOLUME_SETTING]) {
            return emit(response(@"unavailable", @{@"reason": @"unsupported_setting",
                                                   @"supported_settings": @[VOLUME_SETTING]}));
        }
        if ([command isEqualToString:@"get"]) {
            if (argc != 3) {
                return usage();
            }
            return emit(get_volume());
        }
        if ([command isEqualToString:@"set"]) {
            if (argc != 4) {
                return usage();
            }
            double value = 0.0;
            if (!parse_volume(argv[3], &value)) {
                return emit(error_response(@"invalid_value"));
            }
            return emit(set_volume(value));
        }
        return usage();
    }
}
