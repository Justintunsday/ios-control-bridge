// Builds synthetic SAObjects; never records audio or queries Siri/OpenCode.
#import "SiriRuntime.h"
#import <dlfcn.h>

int main(void){@autoreleasepool{
    if(!dlopen("/System/Library/PrivateFrameworks/AssistantServices.framework/AssistantServices",RTLD_NOW))return 2;
    if(!dlopen("/System/Library/PrivateFrameworks/SAObjects.framework/SAObjects",RTLD_NOW))return 2;
    const char *classes[]={"SASToken","SASInterpretation","SASPhrase","SASRecognition","SASUtterance","SASSpeechRecognized"};
    const char *setters[]={"setText:","setTokens:","setInterpretations:","setPhrases:","setInterpretationIndices:","setRecognition:"};
    for(unsigned i=0;i<6;i++)if(!ICBMethod(objc_getClass(classes[i]),setters[i],"v24@0:8@16"))return 3;
    if(!ICBMethod(objc_getClass("SASRecognition"),"setUtterances:","v24@0:8@16"))return 3;
    NSMutableArray *tokens=[NSMutableArray array];
    for(NSString *word in @[@"one",@"plus",@"one"]){id token=[[objc_getClass("SASToken") alloc] init];ICBSet(token,"setText:",word);[tokens addObject:token];}
    id interpretation=[[objc_getClass("SASInterpretation") alloc] init];ICBSet(interpretation,"setTokens:",tokens);
    id phrase=[[objc_getClass("SASPhrase") alloc] init];ICBSet(phrase,"setInterpretations:",@[interpretation]);
    id utterance=[[objc_getClass("SASUtterance") alloc] init];ICBSet(utterance,"setInterpretationIndices:",@[@0]);
    id recognition=[[objc_getClass("SASRecognition") alloc] init];ICBSet(recognition,"setPhrases:",@[phrase]);ICBSet(recognition,"setUtterances:",@[utterance]);
    id recognized=[[objc_getClass("SASSpeechRecognized") alloc] init];ICBSet(recognized,"setRecognition:",recognition);
    id raw=ICBGet(recognized,"af_bestTextInterpretation");NSString *text=ICBRecognitionText(recognized);
    NSDictionary *result=@{@"return_class":raw?NSStringFromClass([raw class]):@"nil",@"synthetic_text":text?:@"",@"passed":@([text isEqual:@"one plus one"])};
    NSData *json=[NSJSONSerialization dataWithJSONObject:result options:0 error:NULL];fwrite(json.bytes,1,json.length,stdout);fputc('\n',stdout);
    // This header also provides the block ABI check used by the injected bridge.
    void (^block)(id,id)=^(id command,id error){(void)command;(void)error;};
    if(!ICBBlockTypes(block))return 4;
    return [text isEqual:@"one plus one"]?0:1;
}}
