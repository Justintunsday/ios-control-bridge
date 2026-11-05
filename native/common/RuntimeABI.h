#ifndef ICB_RUNTIME_ABI_H
#define ICB_RUNTIME_ABI_H
#include <objc/runtime.h>
#include <string.h>

/* Compare the real runtime signature, including offsets on the verified build. */
static BOOL ICBABI(id receiver, const char *selector, const char *encoding) {
    if (!receiver) return NO;
    Method method = class_getInstanceMethod(object_getClass(receiver), sel_registerName(selector));
    return method && strcmp(method_getTypeEncoding(method), encoding) == 0;
}
#endif
