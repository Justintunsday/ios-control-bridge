import base64
import io
import json
import unittest
from tools.iosremote_stdio import Adapter, Server, validate


class Fake:
    instances = []
    def __init__(self, *args, **kwargs):
        self.error = None
        self.calls = []
        self.closed = False
        self.instances.append(self)
    def connect(self): return self
    def close(self): self.closed = True
    def request(self, name, **args):
        self.calls.append((name, args))
        if name == 'get_screen_frame':
            return {'mime':'image/jpeg', 'base64':base64.b64encode(b'jpeg-fixture').decode()}
        if name == 'tap': raise RuntimeError('outcome unknown')
        return {'state':'completed'}


class StdioTests(unittest.TestCase):
    def setUp(self): Fake.instances = []
    def ready(self, control=False):
        a=Adapter('unused', control, factory=Fake)
        s=Server(a)
        s.dispatch({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}})
        s.dispatch({'jsonrpc':'2.0','method':'notifications/initialized'})
        return a,s
    def call(self,s,name,args=None):
        return s.dispatch({'jsonrpc':'2.0','id':5,'method':'tools/call','params':{'name':name,'arguments':args or {}}})['result']
    def test_input_rejected_before_connect(self):
        a,s=self.ready()
        r=self.call(s,'tap',{'x':.5,'y':.5})
        self.assertTrue(r['isError'])
        self.assertIn('input disabled',r['content'][0]['text'])
        self.assertEqual(Fake.instances,[])
    def test_image_is_native_mcp_content(self):
        a,s=self.ready()
        r=self.call(s,'get_screen_frame')
        self.assertFalse(r['isError'])
        self.assertEqual(r['content'][0]['type'],'image')
        self.assertEqual(base64.b64decode(r['content'][0]['data']),b'jpeg-fixture')
    def test_invalid_arguments_do_not_reach_device(self):
        a,s=self.ready(True)
        for args in [{'x':-1,'y':.5},{'x':True,'y':.5},{'x':float('nan'),'y':.5},{'x':.5,'y':.5,'extra':1},{'x':.5}]:
            self.assertTrue(self.call(s,'tap',args)['isError'])
        self.assertTrue(self.call(s,'type_text',{'text':'中文'})['isError'])
        self.assertEqual(Fake.instances,[])
    def test_duration_default_and_integer_limit(self):
        a,s=self.ready(True)
        args={'x':.5,'y':.8,'to_x':.5,'to_y':.2}
        self.assertFalse(self.call(s,'swipe',args)['isError'])
        self.assertEqual(Fake.instances[0].calls[0][1]['duration_ms'],400)
        self.assertTrue(self.call(s,'swipe',dict(args,duration_ms=40.5))['isError'])
    def test_failed_input_is_not_replayed(self):
        a,s=self.ready(True)
        self.assertTrue(self.call(s,'tap',{'x':.5,'y':.5})['isError'])
        self.assertEqual(len(Fake.instances[0].calls),1)
    def test_literal_unicode_is_preserved_and_does_not_enable_keyboard(self):
        a,s=self.ready(True)
        text='AI 直接输入\n你好，世界 😀 café 👩🏽‍💻'
        self.assertFalse(self.call(s,'insert_text',{'text':text})['isError'])
        self.assertEqual(Fake.instances[0].calls,[('insert_text',{'text':text})])
    def test_unicode_boundaries_are_utf16_units_and_reject_unpaired_surrogates(self):
        a,s=self.ready(True)
        self.assertFalse(self.call(s,'insert_text',{'text':'😀'*512})['isError'])
        for text in ['😀'*513,'x'*1025,'\ud800','\udc00']:
            self.assertTrue(self.call(s,'insert_text',{'text':text})['isError'])
        self.assertEqual(len(Fake.instances[0].calls),1)
    def test_literal_input_readonly_gate_precedes_connection(self):
        a,s=self.ready()
        self.assertTrue(self.call(s,'insert_text',{'text':'中文😀'})['isError'])
        self.assertEqual(Fake.instances,[])
    def test_ambiguous_literal_input_does_not_fallback_or_replay(self):
        class Ambiguous(Fake):
            def request(self,name,**args):
                self.calls.append((name,args))
                raise RuntimeError('outcome unknown')
        adapter=Adapter('unused',True,factory=Ambiguous)
        with self.assertRaises(RuntimeError):adapter.call('insert_text',{'text':'中文😀'})
        self.assertEqual(adapter.client.calls,[('insert_text',{'text':'中文😀'})])
    def test_status_is_lazy_and_disconnect_releases(self):
        a,s=self.ready()
        self.assertFalse(json.loads(self.call(s,'get_connection_status')['content'][0]['text'])['connected'])
        self.assertEqual(Fake.instances,[])
        self.call(s,'get_device_info')
        self.call(s,'disconnect')
        self.assertTrue(Fake.instances[0].closed)
        self.assertIsNone(a.client)
    def test_initialization_and_unknown_method(self):
        s=Server(Adapter('unused',factory=Fake))
        request={'jsonrpc':'2.0','id':'before','method':'tools/list'}
        self.assertIn('error',s.dispatch(request))
        a,s=self.ready()
        self.assertEqual(s.dispatch({'jsonrpc':'2.0','id':8,'method':'unknown'})['error']['code'],-32601)
        self.assertIsNone(s.dispatch({'jsonrpc':'2.0','method':'notifications/unknown'}))
    def test_stdio_eof_closes_and_stdout_is_protocol_only(self):
        a,s=self.ready()
        lines=[{'jsonrpc':'2.0','id':9,'method':'tools/call','params':{'name':'get_device_info'}}]
        output=io.BytesIO()
        s.serve(io.BytesIO(b'\n'.join(json.dumps(x).encode() for x in lines)+b'\n'),output)
        result=[json.loads(x) for x in output.getvalue().splitlines()]
        self.assertEqual(len(result),1)
        self.assertFalse(result[0]['result']['isError'])
        self.assertTrue(Fake.instances[0].closed)
    def test_parse_error_and_line_limit_close(self):
        a,s=self.ready()
        output=io.BytesIO()
        s.serve(io.BytesIO(b'{bad\n'+b'x'*65537+b'\n'),output)
        result=[json.loads(x) for x in output.getvalue().splitlines()]
        self.assertEqual([x['error']['code'] for x in result],[-32700,-32600])


if __name__=='__main__':unittest.main()
