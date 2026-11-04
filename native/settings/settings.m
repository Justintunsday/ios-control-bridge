#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
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
 *   icb-settings get brightness
 *   icb-settings set brightness <0.0-1.0>
 *
 * The result is JSON on stdout. Exit status follows the project contract:
 * 0 = verified, 2 = partial, 3 = unavailable, 4 = error.
 */

static NSString *const SETTINGS_SCHEMA = @"ios-control-bridge.settings.v1";
static NSString *const VOLUME_SOURCE = @"AVSystemController";
static NSString *const BRIGHTNESS_SOURCE = @"BrightnessSystemClient";
static NSString *const VOLUME_SETTING = @"volume";
static NSString *const BRIGHTNESS_SETTING = @"brightness";
static NSString *const VOLUME_CATEGORY = @"Audio/Video";
static NSString *const SETTING_UNIT = @"fraction";
static const double VOLUME_TOLERANCE = 0.001;
static const double BRIGHTNESS_TOLERANCE = 0.005;

static NSArray *supported_settings(void) {
    return @[VOLUME_SETTING, BRIGHTNESS_SETTING];
}

static NSDictionary *base_response(NSString *status, NSString *setting, NSString *source,
                                   NSDictionary *details) {
    NSMutableDictionary *payload = [NSMutableDictionary dictionary];
    payload[@"schema"] = SETTINGS_SCHEMA;
    payload[@"status"] = status;
    payload[@"setting"] = setting ?: @"";
    payload[@"source"] = source ?: @"";
    payload[@"observed_at_unix"] = @((double)time(NULL));
    if (details) {
        [payload addEntriesFromDictionary:details];
    }
    return payload;
}

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

static NSDictionary *error_response(NSString *setting, NSString *source, NSString *reason) {
    return base_response(@"error", setting, source, @{@"reason": reason});
}

static NSDictionary *unavailable_setting(NSString *setting) {
    return base_response(@"unavailable", setting, @"", @{
        @"reason": @"unsupported_setting",
        @"supported_settings": supported_settings()
    });
}

#pragma mark - Volume (AVSystemController)

static id volume_controller(void) {
    Class cls = NSClassFromString(@"AVSystemController");
    if (!cls) {
        return nil;
    }
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
    id controller = volume_controller();
    if (!controller) {
        return base_response(@"unavailable", VOLUME_SETTING, VOLUME_SOURCE,
                             @{@"reason": @"system_class_unavailable"});
    }
    float value = -1.0f;
    if (!read_volume(controller, &value)) {
        return error_response(VOLUME_SETTING, VOLUME_SOURCE, @"read_failed");
    }
    return base_response(@"verified", VOLUME_SETTING, VOLUME_SOURCE, @{
        @"value": @(value),
        @"range": @{@"min": @(0.0), @"max": @(1.0)},
        @"unit": SETTING_UNIT
    });
}

static NSDictionary *set_volume(double requested) {
    id controller = volume_controller();
    if (!controller) {
        return base_response(@"unavailable", VOLUME_SETTING, VOLUME_SOURCE,
                             @{@"reason": @"system_class_unavailable"});
    }
    float before = -1.0f;
    if (!read_volume(controller, &before)) {
        return error_response(VOLUME_SETTING, VOLUME_SOURCE, @"read_before_failed");
    }
    if (!write_volume(controller, (float)requested)) {
        return error_response(VOLUME_SETTING, VOLUME_SOURCE, @"write_failed");
    }
    usleep(200000);
    float readback = -1.0f;
    if (!read_volume(controller, &readback)) {
        return error_response(VOLUME_SETTING, VOLUME_SOURCE, @"readback_failed");
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
        @"category": VOLUME_CATEGORY,
        @"range": @{@"min": @(0.0), @"max": @(1.0)},
        @"unit": SETTING_UNIT
    } mutableCopy];
    if (!verified) {
        details[@"reason"] = @"readback_mismatch";
    }
    return base_response(verified ? @"verified" : @"partial", VOLUME_SETTING, VOLUME_SOURCE, details);
}

#pragma mark - Display brightness (BrightnessSystemClient)

static id brightness_client(void) {
    Class cls = NSClassFromString(@"BrightnessSystemClient");
    if (!cls) {
        return nil;
    }
    SEL initialize = sel_registerName("init");
    return ((id (*)(id, SEL))objc_msgSend)((id)[cls alloc], initialize);
}

static id copy_brightness_property(NSString *key) {
    id client = brightness_client();
    if (!client) {
        return nil;
    }
    SEL selector = sel_registerName("copyPropertyForKey:");
    return ((id (*)(id, SEL, id))objc_msgSend)(client, selector, key);
}

static NSDictionary *brightness_dictionary(void) {
    id value = copy_brightness_property(@"DisplayBrightness");
    if (![value isKindOfClass:[NSDictionary class]]) {
        return nil;
    }
    return value;
}

static BOOL read_brightness(double *value, double *nits) {
    NSDictionary *dictionary = brightness_dictionary();
    if (!dictionary) {
        return NO;
    }
    id brightness = dictionary[@"Brightness"];
    if (![brightness isKindOfClass:[NSNumber class]]) {
        return NO;
    }
    if (value) {
        *value = [brightness doubleValue];
    }
    if (nits && [dictionary[@"Nits"] isKindOfClass:[NSNumber class]]) {
        *nits = [dictionary[@"Nits"] doubleValue];
    }
    return YES;
}

static BOOL write_brightness(double value) {
    id client = brightness_client();
    if (!client) {
        return NO;
    }
    SEL selector = sel_registerName("setProperty:forKey:");
    return ((BOOL (*)(id, SEL, id, id))objc_msgSend)(client, selector, @(value), @"DisplayBrightness");
}

static NSDictionary *get_brightness(void) {
    if (!brightness_client()) {
        return base_response(@"unavailable", BRIGHTNESS_SETTING, BRIGHTNESS_SOURCE,
                             @{@"reason": @"system_class_unavailable"});
    }
    double value = -1.0;
    double nits = -1.0;
    if (!read_brightness(&value, &nits)) {
        return error_response(BRIGHTNESS_SETTING, BRIGHTNESS_SOURCE, @"read_failed");
    }
    NSMutableDictionary *details = [@{
        @"value": @(value),
        @"range": @{@"min": @(0.0), @"max": @(1.0)},
        @"unit": SETTING_UNIT
    } mutableCopy];
    if (nits >= 0.0) {
        details[@"nits"] = @(nits);
    }
    return base_response(@"verified", BRIGHTNESS_SETTING, BRIGHTNESS_SOURCE, details);
}

static NSDictionary *set_brightness(double requested) {
    if (!brightness_client()) {
        return base_response(@"unavailable", BRIGHTNESS_SETTING, BRIGHTNESS_SOURCE,
                             @{@"reason": @"system_class_unavailable"});
    }
    double before = -1.0;
    if (!read_brightness(&before, NULL)) {
        return error_response(BRIGHTNESS_SETTING, BRIGHTNESS_SOURCE, @"read_before_failed");
    }
    if (!write_brightness(requested)) {
        return error_response(BRIGHTNESS_SETTING, BRIGHTNESS_SOURCE, @"write_failed");
    }
    usleep(250000);
    double readback = -1.0;
    if (!read_brightness(&readback, NULL)) {
        return error_response(BRIGHTNESS_SETTING, BRIGHTNESS_SOURCE, @"readback_failed");
    }
    double delta = readback - requested;
    BOOL verified = fabs(delta) <= BRIGHTNESS_TOLERANCE;
    NSMutableDictionary *details = [@{
        @"before": @(before),
        @"requested": @(requested),
        @"readback": @(readback),
        @"delta": @(delta),
        @"tolerance": @(BRIGHTNESS_TOLERANCE),
        @"verified": @(verified),
        @"range": @{@"min": @(0.0), @"max": @(1.0)},
        @"unit": SETTING_UNIT
    } mutableCopy];
    if (!verified) {
        details[@"reason"] = @"readback_mismatch";
    }
    return base_response(verified ? @"verified" : @"partial", BRIGHTNESS_SETTING, BRIGHTNESS_SOURCE, details);
}

#pragma mark - Entry point

static BOOL parse_value(const char *text, double *value) {
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
    fprintf(stderr, "usage: icb-settings get volume|brightness\n");
    fprintf(stderr, "       icb-settings set volume|brightness <0.0-1.0>\n");
    return 4;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        if (argc < 3) {
            return usage();
        }
        NSString *command = [NSString stringWithUTF8String:argv[1]];
        NSString *setting = [NSString stringWithUTF8String:argv[2]];
        if (![setting isEqualToString:VOLUME_SETTING] && ![setting isEqualToString:BRIGHTNESS_SETTING]) {
            return emit(unavailable_setting(setting));
        }
        if ([command isEqualToString:@"get"]) {
            if (argc != 3) {
                return usage();
            }
            return emit([setting isEqualToString:VOLUME_SETTING] ? get_volume() : get_brightness());
        }
        if ([command isEqualToString:@"set"]) {
            if (argc != 4) {
                return usage();
            }
            double value = 0.0;
            if (!parse_value(argv[3], &value)) {
                NSString *source = [setting isEqualToString:VOLUME_SETTING] ? VOLUME_SOURCE : BRIGHTNESS_SOURCE;
                return emit(error_response(setting, source, @"invalid_value"));
            }
            return emit([setting isEqualToString:VOLUME_SETTING] ? set_volume(value) : set_brightness(value));
        }
        return usage();
    }
}
