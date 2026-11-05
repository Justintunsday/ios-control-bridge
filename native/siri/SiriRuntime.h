#import <Foundation/Foundation.h>
#import <objc/message.h>
#import <objc/runtime.h>
#import <string.h>

static BOOL ICBMethod(Class cls,const char *name,const char *types) {
    Method method=class_getInstanceMethod(cls,sel_registerName(name));
    return method&&strcmp(method_getTypeEncoding(method),types)==0;
}
static id ICBGet(id object,const char *name) {
    if(!object||!ICBMethod(object_getClass(object),name,"@16@0:8"))return nil;
    return ((id(*)(id,SEL))objc_msgSend)(object,sel_registerName(name));
}
static void ICBSet(id object,const char *name,id value) {
    ((void(*)(id,SEL,id))objc_msgSend)(object,sel_registerName(name),value);
}
static NSString *ICBRecognitionText(id recognized) {
    if(![recognized isKindOfClass:objc_getClass("SASSpeechRecognized")])return nil;
    id value=ICBGet(recognized,"af_bestTextInterpretation");
    // On 20B101 this category returns an NSString, not an arbitrary description.
    if(![value isKindOfClass:NSString.class]||![value length]||[value length]>4096)return nil;
    return value;
}
static const char *ICBBlockTypes(id value) {
    if(!value)return NULL;
    struct Layout { void *isa; int flags,reserved; void *invoke; void *descriptor; };
    const struct Layout *block=(__bridge const void *)value;
    if(!(block->flags&(1<<30))||!block->descriptor)return NULL;
    const uint8_t *p=block->descriptor;
    p+=sizeof(unsigned long)*2;
    if(block->flags&(1<<25))p+=sizeof(void *)*2;
    return *(const char *const *)p;
}
